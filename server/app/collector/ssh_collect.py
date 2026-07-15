from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import asyncssh

from ..config import AppConfig, resolve_auth
from ..models import HostStatus, ProcessInfo, UserInfo


WHO_CMD = "LANG=C who -u 2>/dev/null || LANG=C who"
HOSTNAME_CMD = "hostname -s 2>/dev/null || hostname"
# Host totals: nproc  MemTotal_kB  MemAvailable_kB  host_cpu%  host_mem%
HOST_INFO_CMD = (
    "nproc=$(nproc 2>/dev/null || echo 1); "
    "mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo); "
    "avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo); "
    "cpu=$(grep -m1 '^cpu ' /proc/stat | awk '{u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; "
    "if(t>0) printf \"%.1f\", 100*u/t; else printf \"0.0\"}'); "
    "mem=$(awk -v t=\"$mem_kb\" -v a=\"$avail_kb\" 'BEGIN{"
    "if(t>0) printf \"%.1f\", 100*(t-a)/t; else printf \"0.0\"}'); "
    "echo \"$nproc $mem_kb $avail_kb $cpu $mem\""
)

# who -u sample: user pts/0 2024-01-01 12:00 . 12345 (1.2.3.4)
WHO_RE = re.compile(
    r"^(?P<user>\S+)\s+\S+\s+(?P<rest>.+)$"
)


@dataclass
class HostCollectResult:
    status: HostStatus
    users: List[UserInfo] = field(default_factory=list)
    processes: dict[str, List[ProcessInfo]] = field(default_factory=dict)
    host_top: List[ProcessInfo] = field(default_factory=list)
    host_cpu: float = 0.0
    host_mem: float = 0.0


def parse_host_top_ps(output: str, nproc: int = 1) -> List[ProcessInfo]:
    """Parse host-wide ``ps -eo user,pid,%cpu,%mem,etime,comm`` top lines."""
    procs: List[ProcessInfo] = []
    now = datetime.now().astimezone()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        if len(parts) == 5:
            user, pid, cpu_s, mem_s, etime = parts
            name = "?"
        else:
            user, pid, cpu_s, mem_s, etime, name = parts
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
                user=user,
                cpuUsage=round(min(cpu, 100.0), 1),
                memoryUsage=round(min(mem, 100.0), 1),
                startTime=_etime_to_start(etime, now),
            )
        )
    procs.sort(key=lambda p: (p.cpuUsage + p.memoryUsage), reverse=True)
    return procs[:5]


def _parse_login_time(rest: str) -> datetime:
    """Best-effort parse of who leftover fields for login timestamp."""
    now = datetime.now().astimezone()
    # ISO-ish: 2024-07-14 16:20
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", rest)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").astimezone()
        except ValueError:
            pass
    # Legacy: Jul 14 16:20
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
        # Filter system/noise lines
        if user in {"reboot", "runlevel", "shutdown", "LOGIN"}:
            continue
        login = _parse_login_time(m.group("rest"))
        if user not in seen or login < seen[user]:
            seen[user] = login
    return list(seen.items())


def parse_host_info(output: str) -> Tuple[int, int, int, float, float]:
    """Return nproc, mem_total_kb, mem_avail_kb, host_cpu_pct, host_mem_pct."""
    nums = re.findall(r"\d+(?:\.\d+)?", output.strip())
    if len(nums) < 5:
        if len(nums) >= 4:
            # backward-compatible: nproc total cpu% mem%
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


def parse_user_host_share(output: str, nproc: int, mem_total_kb: int) -> Tuple[float, float, int]:
    """
    User share of the whole host.

    Returns (cpu_pct, mem_pct, estimated_rss_kb).
    - CPU: sum(ps %cpu) / nproc
    - Memory: estimated unique RSS / MemTotal (see estimate_user_rss_kb)
    """
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


def parse_ps(output: str, username: str, nproc: int = 1) -> List[ProcessInfo]:
    """Top processes; cpuUsage/memoryUsage are share of the whole host."""
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
            # ps %cpu is relative to one core; normalize to host capacity
            cpu = float(cpu_s) / max(nproc, 1)
            # ps %mem is already percent of physical memory
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
        # Prefer password when profile says so
        if not auth.use_key:
            connect_kwargs.pop("client_keys", None)

    async with sem:
        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                raw_hostname = await _run(conn, HOSTNAME_CMD, cfg.command_timeout)
                # Prefer short hostname so dual-homed VMs collapse to one name
                hostname = (raw_hostname.split(".", 1)[0] if raw_hostname else host).strip() or host

                # If we connected by IP but hostname matches a password profile, still fine.
                # If connected by default key but host is actually a tbn that we hit via IP only,
                # next refresh with explicit hostname list will use root.

                who_out = await _run(conn, WHO_CMD, cfg.command_timeout)
                info_out = await _run(conn, HOST_INFO_CMD, cfg.command_timeout)
                nproc, mem_total_kb, mem_avail_kb, host_cpu, host_mem = parse_host_info(info_out)
                sessions = parse_who(who_out)

                # Host-wide top processes (any user)
                host_ps_cmd = (
                    "ps -eo user:24,pid=,%cpu=,%mem=,etime=,comm= --sort=-%cpu 2>/dev/null | head -n 12"
                )
                host_ps_out = await _run(conn, host_ps_cmd, cfg.command_timeout)
                host_top = parse_host_top_ps(host_ps_out, nproc=nproc)

                users: List[UserInfo] = []
                processes: dict[str, List[ProcessInfo]] = {}
                rss_by_user: Dict[str, int] = {}

                for username, login_time in sessions:
                    quoted = "'" + username.replace("'", "'\\''") + "'"
                    usage_cmd = f"ps -u {quoted} -o %cpu=,rss=,comm= --no-headers 2>/dev/null"
                    ps_cmd = (
                        f"ps -u {quoted} -o pid=,%cpu=,%mem=,etime=,comm= "
                        f"--sort=-%cpu 2>/dev/null | head -n 8"
                    )
                    usage_out, ps_out = await asyncio.gather(
                        _run(conn, usage_cmd, cfg.command_timeout),
                        _run(conn, ps_cmd, cfg.command_timeout),
                    )
                    user_cpu, user_mem, rss_kb = parse_user_host_share(
                        usage_out, nproc, mem_total_kb
                    )
                    rss_by_user[username] = rss_kb
                    top = parse_ps(ps_out, username, nproc=nproc)
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