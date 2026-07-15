from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

import asyncssh

from ..config import AppConfig, resolve_auth
from ..models import HostStatus, ProcessInfo, UserInfo


WHO_CMD = "LANG=C who -u 2>/dev/null || LANG=C who"
HOSTNAME_CMD = "hostname -s 2>/dev/null || hostname"

# Fast host metrics: loadavg-based CPU (no sleep) + MemAvailable mem%
HOST_INFO_CMD = (
    "nproc=$(nproc 2>/dev/null || echo 1); "
    "mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo); "
    "avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo); "
    "load=$(awk '{print $1}' /proc/loadavg); "
    "cpu=$(awk -v l=\"$load\" -v n=\"$nproc\" "
    "'BEGIN{v=100.0*l/n; if(v>100)v=100; if(v<0)v=0; printf \"%.1f\", v}'); "
    "mem=$(awk -v t=\"$mem_kb\" -v a=\"$avail_kb\" 'BEGIN{"
    "if(t>0) printf \"%.1f\", 100*(t-a)/t; else printf \"0.0\"}'); "
    "echo \"$nproc $mem_kb $avail_kb $cpu $mem\""
)

# Single process table for host top + per-user share (avoid N× ssh roundtrips)
PS_ALL_CMD = (
    "ps -eo user:32,pid=,%cpu=,%mem=,rss=,etime=,comm= --sort=-%cpu 2>/dev/null | head -n 800"
)

# who -u sample: user pts/0 2024-01-01 12:00 . 12345 (1.2.3.4)
WHO_RE = re.compile(r"^(?P<user>\S+)\s+\S+\s+(?P<rest>.+)$")

_SYSTEM_USERS = frozenset(
    {
        "root",
        "daemon",
        "bin",
        "sys",
        "sync",
        "games",
        "man",
        "lp",
        "mail",
        "news",
        "uucp",
        "proxy",
        "www-data",
        "backup",
        "list",
        "irc",
        "gnats",
        "nobody",
        "systemd-network",
        "systemd-resolve",
        "systemd-timesync",
        "messagebus",
        "dbus",
        "polkitd",
        "rtkit",
        "colord",
        "gdm",
        "avahi",
        "rpc",
        "munge",
        "chrony",
        "ollama",
        "libstoragemgmt",
        "sshd",
        "_apt",
        "tss",
        "usbmux",
        "flatpak",
        "reboot",
        "runlevel",
        "shutdown",
        "LOGIN",
    }
)

# Spawned by SSH login / desktop session — not real cluster work.
# Also ignore brand-new processes (etime < 5s): %cpu spikes from monitoring SSH.
_SESSION_NOISE_COMM = frozenset(
    {
        "systemd",
        "(sd-pam)",
        "snap",
        "snapd",
        "snapd-desktop-integration",
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "dbus-daemon",
        "sshd",
        "ssh",
        "bash",
        "sh",
        "zsh",
        "ps",
        "head",
        "sleep",
        "cat",
        "awk",
        "sed",
        "grep",
        "sudo",
        "su",
        "tmux",
        "screen",
        "gvfsd",
        "ibus-daemon",
        "at-spi-bus-launcher",
        "xdg-permission-store",
        "xdg-document-portal",
        "xdg-desktop-portal",
        "xdg-desktop-portal-gtk",
    }
)


@dataclass
class HostCollectResult:
    status: HostStatus
    users: List[UserInfo] = field(default_factory=list)
    processes: dict[str, List[ProcessInfo]] = field(default_factory=dict)
    host_top: List[ProcessInfo] = field(default_factory=list)
    host_cpu: float = 0.0
    host_mem: float = 0.0


@dataclass
class _PsRow:
    user: str
    pid: str
    cpu: float
    mem: float
    rss: int
    etime: str
    comm: str


def parse_host_top_ps(output: str, nproc: int = 1) -> List[ProcessInfo]:
    """Parse host-wide ``ps -eo user,pid,%cpu,%mem,etime,comm`` top lines."""
    rows = parse_ps_all(output)
    now = datetime.now().astimezone()
    procs: List[ProcessInfo] = []
    for r in rows[:12]:
        procs.append(
            ProcessInfo(
                pid=r.pid,
                name=r.comm[:64],
                user=r.user,
                cpuUsage=round(min(r.cpu / max(nproc, 1), 100.0), 1),
                memoryUsage=round(min(r.mem, 100.0), 1),
                startTime=_etime_to_start(r.etime, now),
            )
        )
    procs.sort(key=lambda p: (p.cpuUsage + p.memoryUsage), reverse=True)
    return procs[:5]


def parse_ps_all(output: str) -> List[_PsRow]:
    rows: List[_PsRow] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        if len(parts) == 6:
            user, pid, cpu_s, mem_s, rss_s, etime = parts
            comm = "?"
        else:
            user, pid, cpu_s, mem_s, rss_s, etime, comm = parts
        if pid.lower() == "pid" or user.lower() == "user":
            continue
        try:
            rows.append(
                _PsRow(
                    user=user,
                    pid=pid,
                    cpu=float(cpu_s),
                    mem=float(mem_s),
                    rss=int(float(rss_s)),
                    etime=etime,
                    comm=comm[:64],
                )
            )
        except ValueError:
            continue
    return rows


def _parse_login_time(rest: str) -> datetime:
    """Best-effort parse of who leftover fields for login timestamp."""
    now = datetime.now().astimezone()
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", rest)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").astimezone()
        except ValueError:
            pass
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{1,2}:\d{2})",
        rest,
    )
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %H:%M")
            dt = dt.replace(year=now.year, tzinfo=now.tzinfo)
            if dt > now + timedelta(days=1):
                dt = dt.replace(year=now.year - 1)
            return dt
        except ValueError:
            pass
    return now


def parse_who(output: str) -> List[Tuple[str, datetime]]:
    seen: dict[str, datetime] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = WHO_RE.match(line)
        if not m:
            continue
        user = m.group("user")
        if user in {"reboot", "runlevel", "shutdown", "LOGIN"}:
            continue
        login = _parse_login_time(m.group("rest"))
        if user not in seen or login < seen[user]:
            seen[user] = login
    return list(seen.items())


def _etime_seconds(etime: str) -> int:
    try:
        days = 0
        rest = etime
        if "-" in etime:
            day_s, rest = etime.split("-", 1)
            days = int(day_s)
        parts = [int(x) for x in rest.split(":")]
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = 0, parts[0], parts[1]
        else:
            return 0
        return days * 86400 + h * 3600 + m * 60 + s
    except Exception:
        return 0


def _is_session_noise(r: _PsRow) -> bool:
    base = r.comm.rsplit("/", 1)[-1].lower()
    if base in _SESSION_NOISE_COMM or base.startswith("xdg-"):
        return True
    # Fresh processes from collector SSH / login hooks inflate %cpu meaningless
    if _etime_seconds(r.etime) < 5:
        return True
    return False


def active_users_from_ps(rows: List[_PsRow]) -> List[str]:
    """Users with real work (no TTY needed): sum(%cpu)>=5 or rss>=200MB."""
    cpu: Dict[str, float] = defaultdict(float)
    rss: Dict[str, int] = defaultdict(int)
    for r in rows:
        if r.user in _SYSTEM_USERS or _is_session_noise(r):
            continue
        cpu[r.user] += r.cpu
        rss[r.user] += r.rss
    return [u for u in cpu if cpu[u] >= 5.0 or rss[u] >= 204800]


def merge_monitored_users(
    who_sessions: List[Tuple[str, datetime]],
    active_users: List[str],
    now: datetime,
) -> List[Tuple[str, datetime]]:
    """Union of TTY logins (who) and busy process owners (no TTY)."""
    by_user: dict[str, datetime] = {u: t for u, t in who_sessions}
    for u in active_users:
        if u not in by_user:
            by_user[u] = now
    return list(by_user.items())


def parse_host_info(output: str) -> Tuple[int, int, int, float, float]:
    """Return nproc, mem_total_kb, mem_avail_kb, host_cpu_pct, host_mem_pct."""
    nums = re.findall(r"\d+(?:\.\d+)?", output.strip())
    if len(nums) < 5:
        if len(nums) >= 4:
            nproc = max(int(float(nums[0])), 1)
            mem_kb = max(int(float(nums[1])), 1)
            return nproc, mem_kb, 0, float(nums[2]), float(nums[3])
        return 1, 1, 0, 0.0, 0.0
    nproc = max(int(float(nums[0])), 1)
    mem_kb = max(int(float(nums[1])), 1)
    avail_kb = max(int(float(nums[2])), 0)
    return nproc, mem_kb, avail_kb, float(nums[3]), float(nums[4])


def estimate_user_rss_kb(rss_by_comm: Dict[str, List[int]]) -> int:
    """
    Estimate unique RAM for a user.

    Plain sum(RSS) double-counts shared/COW pages (common for EDA worker farms
    like many identical RainaSynth processes). If same ``comm`` have similar RSS,
    count once (max); if sizes diverge, treat as independent jobs and sum.
    """
    total = 0
    for values in rss_by_comm.values():
        if not values:
            continue
        if len(values) == 1:
            total += values[0]
            continue
        mx, mn = max(values), min(values)
        if mx > 0 and (mx - mn) / mx <= 0.20:
            total += mx
        else:
            total += sum(values)
    return total


def user_share_from_rows(
    rows: List[_PsRow], nproc: int, mem_total_kb: int
) -> Tuple[float, float, int]:
    cpu_sum = 0.0
    by_comm: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        if _is_session_noise(r):
            continue
        cpu_sum += r.cpu
        by_comm[r.comm].append(r.rss)
    rss_kb = estimate_user_rss_kb(by_comm)
    cpu_pct = round(min(cpu_sum / max(nproc, 1), 100.0), 1)
    mem_pct = round(min(100.0 * rss_kb / max(mem_total_kb, 1), 100.0), 1)
    return cpu_pct, mem_pct, rss_kb


def parse_user_host_share(output: str, nproc: int, mem_total_kb: int) -> Tuple[float, float, int]:
    """Legacy text format: ``%cpu rss comm`` lines."""
    cpu_sum = 0.0
    by_comm: Dict[str, List[int]] = defaultdict(list)
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        try:
            cpu_sum += float(parts[0])
            rss = int(float(parts[1]))
        except ValueError:
            continue
        comm = parts[2] if len(parts) > 2 else "?"
        by_comm[comm].append(rss)

    rss_kb = estimate_user_rss_kb(by_comm)
    cpu_pct = round(min(cpu_sum / max(nproc, 1), 100.0), 1)
    mem_pct = round(min(100.0 * rss_kb / max(mem_total_kb, 1), 100.0), 1)
    return cpu_pct, mem_pct, rss_kb


def rescale_user_memory(
    users: List[UserInfo],
    rss_by_user: Dict[str, int],
    mem_total_kb: int,
    mem_avail_kb: int,
) -> None:
    """If online users' estimated RSS exceeds host used memory, scale down pro-rata."""
    claimed = sum(max(0, rss_by_user.get(u.username, 0)) for u in users)
    used = max(mem_total_kb - mem_avail_kb, 0) if mem_avail_kb > 0 else 0
    if claimed <= 0 or used <= 0 or claimed <= used:
        return
    scale = used / claimed
    for u in users:
        rss = rss_by_user.get(u.username, 0)
        u.memoryUsage = round(min(100.0 * rss * scale / max(mem_total_kb, 1), 100.0), 1)


def top_procs_for_user(rows: List[_PsRow], username: str, nproc: int, now: datetime) -> List[ProcessInfo]:
    procs: List[ProcessInfo] = []
    for r in rows:
        if r.user != username:
            continue
        procs.append(
            ProcessInfo(
                pid=r.pid,
                name=r.comm[:64],
                user=username,
                cpuUsage=round(min(r.cpu / max(nproc, 1), 100.0), 1),
                memoryUsage=round(min(r.mem, 100.0), 1),
                startTime=_etime_to_start(r.etime, now),
            )
        )
    procs.sort(key=lambda p: (p.cpuUsage + p.memoryUsage), reverse=True)
    return procs[:5]


def parse_ps(output: str, username: str, nproc: int = 1) -> List[ProcessInfo]:
    """Top processes from ``pid %cpu %mem etime comm`` lines."""
    procs: List[ProcessInfo] = []
    now = datetime.now().astimezone()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        if len(parts) == 4:
            pid, cpu_s, mem_s, etime = parts
            name = "?"
        else:
            pid, cpu_s, mem_s, etime, name = parts
        if pid.lower() == "pid":
            continue
        try:
            cpu = float(cpu_s) / max(nproc, 1)
            mem = float(mem_s)
        except ValueError:
            continue
        procs.append(
            ProcessInfo(
                pid=pid,
                name=name[:64],
                user=username,
                cpuUsage=round(min(cpu, 100.0), 1),
                memoryUsage=round(min(mem, 100.0), 1),
                startTime=_etime_to_start(etime, now),
            )
        )
    procs.sort(key=lambda p: (p.cpuUsage + p.memoryUsage), reverse=True)
    return procs[:5]


def _etime_to_start(etime: str, now: datetime) -> datetime:
    """Parse ps etime [[dd-]hh:]mm:ss into approximate start time."""
    try:
        days = 0
        rest = etime
        if "-" in etime:
            day_s, rest = etime.split("-", 1)
            days = int(day_s)
        parts = [int(x) for x in rest.split(":")]
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = 0, parts[0], parts[1]
        else:
            return now
        delta = timedelta(days=days, hours=h, minutes=m, seconds=s)
        return now - delta
    except Exception:
        return now


def _oldest_start(rows: List[_PsRow], now: datetime) -> datetime:
    if not rows:
        return now
    starts = [_etime_to_start(r.etime, now) for r in rows]
    return min(starts)


async def _run(conn: asyncssh.SSHClientConnection, cmd: str, timeout: float) -> str:
    result = await asyncio.wait_for(conn.run(cmd, check=False), timeout=timeout)
    return (result.stdout or "").strip()


async def collect_host(
    host: str,
    cfg: AppConfig,
    key_path: Path,
    sem: asyncio.Semaphore,
) -> HostCollectResult:
    auth = resolve_auth(host, cfg)
    connect_kwargs = {
        "host": host,
        "username": auth.username,
        "known_hosts": None,
        "connect_timeout": cfg.connect_timeout,
        "login_timeout": cfg.connect_timeout,
    }
    if auth.use_key and key_path:
        connect_kwargs["client_keys"] = [str(key_path)]
    if auth.password:
        connect_kwargs["password"] = auth.password
        if not auth.use_key:
            connect_kwargs.pop("client_keys", None)

    async with sem:
        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                raw_hostname = await _run(conn, HOSTNAME_CMD, cfg.command_timeout)
                hostname = (raw_hostname.split(".", 1)[0] if raw_hostname else host).strip() or host

                # Three remote commands only (was: who + active + hostinfo@0.4s + N×ps)
                who_out, info_out, ps_out = await asyncio.gather(
                    _run(conn, WHO_CMD, cfg.command_timeout),
                    _run(conn, HOST_INFO_CMD, cfg.command_timeout),
                    _run(conn, PS_ALL_CMD, cfg.command_timeout),
                )
                nproc, mem_total_kb, mem_avail_kb, host_cpu, host_mem = parse_host_info(info_out)
                now_ts = datetime.now().astimezone()
                ps_rows = parse_ps_all(ps_out)
                sessions = merge_monitored_users(
                    parse_who(who_out),
                    active_users_from_ps(ps_rows),
                    now_ts,
                )
                host_top = parse_host_top_ps(ps_out, nproc=nproc)

                by_user: Dict[str, List[_PsRow]] = defaultdict(list)
                for r in ps_rows:
                    by_user[r.user].append(r)

                users: List[UserInfo] = []
                processes: dict[str, List[ProcessInfo]] = {}
                rss_by_user: Dict[str, int] = {}
                who_names: Set[str] = {u for u, _ in parse_who(who_out)}

                for username, login_time in sessions:
                    urows = by_user.get(username, [])
                    if username not in who_names and urows:
                        login_time = _oldest_start(urows, now_ts)
                    user_cpu, user_mem, rss_kb = user_share_from_rows(
                        urows, nproc, mem_total_kb
                    )
                    rss_by_user[username] = rss_kb
                    top = top_procs_for_user(urows, username, nproc, now_ts)
                    processes[f"{username}@{hostname}"] = top
                    processes[f"{username}@{host}"] = top
                    users.append(
                        UserInfo(
                            id=f"{username}@{hostname}",
                            username=username,
                            vmName=hostname,
                            vmIp=host,
                            cpuUsage=user_cpu,
                            memoryUsage=user_mem,
                            loginTime=login_time,
                        )
                    )

                # Include root only when in who (already handled) — ok
                rescale_user_memory(users, rss_by_user, mem_total_kb, mem_avail_kb)

                detail = "ok"
                if auth.profile_name != "default":
                    detail = f"ok auth={auth.profile_name}"

                return HostCollectResult(
                    status=HostStatus(
                        ip=host,
                        hostname=hostname,
                        status="ok",
                        detail=detail,
                        onlineUsers=len(users),
                    ),
                    users=users,
                    processes=processes,
                    host_top=host_top,
                    host_cpu=host_cpu,
                    host_mem=host_mem,
                )
        except asyncssh.PermissionDenied as exc:
            hint = (
                f"auth failed via {auth.profile_name} as {auth.username}"
                if auth.profile_name != "default"
                else "auth failed (check SSSD/AuthorizedKeys)"
            )
            return HostCollectResult(
                status=HostStatus(
                    ip=host,
                    status="auth_failed",
                    detail=f"{hint}: {exc}",
                )
            )
        except (asyncssh.Error, asyncio.TimeoutError, OSError) as exc:
            msg = str(exc).lower()
            status = "unreachable" if "connect" in msg or "timeout" in msg else "error"
            return HostCollectResult(
                status=HostStatus(ip=host, status=status, detail=str(exc)[:200])
            )
        except Exception as exc:  # noqa: BLE001
            return HostCollectResult(
                status=HostStatus(ip=host, status="error", detail=str(exc)[:200])
            )
