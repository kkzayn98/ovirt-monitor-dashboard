from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..config import ROOT, AppConfig, get_config, resolve_ssh_key
from ..models import Alert, ClusterStats, HostStatus, ProcessInfo, RefreshMeta, Snapshot, UserInfo
from ..alerts import AlertNotifier, build_alerts, is_tbn_host
from .discover import expand_targets, filter_reachable
from .ssh_collect import HostCollectResult, collect_host

logger = logging.getLogger(__name__)


def _prefer_ip(a: str, b: str) -> str:
    """Prefer 192.168.15.x over 192.168.10.x when keeping one IP for a dual-homed host."""
    def score(ip: str) -> Tuple[int, str]:
        if ip.startswith("192.168.15."):
            return (0, ip)
        if ip.startswith("192.168.10."):
            return (1, ip)
        return (2, ip)

    return a if score(a) <= score(b) else b


def _hostname_key(status: HostStatus) -> str:
    if status.hostname:
        return status.hostname.lower()
    return status.ip


class CollectorService:
    def __init__(self, cfg: Optional[AppConfig] = None) -> None:
        self.cfg = cfg or get_config()
        self._lock = asyncio.Lock()
        self._refreshing = False
        self._task: Optional[asyncio.Task] = None
        self._snapshot = Snapshot(
            stats=ClusterStats(
                onlineUsers=0,
                totalVMs=0,
                totalCpuUsage=0,
                totalMemoryUsage=0,
            )
        )
        self._prev_ok_keys: Set[str] = set()
        self._notifier = AlertNotifier()

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    async def start(self) -> None:
        # Don't block API startup on full CIDR scan; first collect runs in background.
        asyncio.create_task(self.refresh())
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.refresh_interval_seconds)
            try:
                await self.refresh()
            except Exception:  # noqa: BLE001
                logger.exception("background refresh failed")

    async def refresh(self) -> Snapshot:
        async with self._lock:
            if self._refreshing:
                return self._snapshot
            self._refreshing = True
            self._snapshot.meta = RefreshMeta(
                lastRefresh=self._snapshot.meta.lastRefresh,
                refreshing=True,
                error=self._snapshot.meta.error,
            )

        try:
            snap = await self._collect_once()
            async with self._lock:
                self._snapshot = snap
                return snap
        except Exception as exc:  # noqa: BLE001
            logger.exception("collect failed")
            async with self._lock:
                self._snapshot.meta = RefreshMeta(
                    lastRefresh=self._snapshot.meta.lastRefresh,
                    refreshing=False,
                    error=str(exc),
                )
                return self._snapshot
        finally:
            async with self._lock:
                self._refreshing = False
                self._snapshot.meta.refreshing = False

    def _write_failed_hosts_log(self, failed: List[HostStatus], now: datetime) -> Path:
        log_path = Path(self.cfg.failed_hosts_log)
        if not log_path.is_absolute():
            log_path = ROOT / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# SSH failed hosts — refreshed at {now.isoformat()}",
            "# Port-open hosts that failed auth/collect. Port-closed CIDR noise is omitted.",
            "# Columns: ip  status  detail",
            "# Review this list to decide whether the machine should be monitored.",
            "",
        ]
        for h in sorted(failed, key=lambda x: (x.status, x.ip)):
            detail = (h.detail or "").replace("\n", " ")[:180]
            lines.append(f"{h.ip}\t{h.status}\t{detail}")

        text = "\n".join(lines) + "\n"
        log_path.write_text(text, encoding="utf-8")
        logger.info("wrote %d SSH failed hosts to %s", len(failed), log_path)
        return log_path

    def _dedupe_ok_hosts(
        self, ok_results: List[HostCollectResult]
    ) -> Tuple[
        List[HostStatus],
        List[UserInfo],
        Dict[str, List[ProcessInfo]],
        Dict[str, List[ProcessInfo]],
        List[float],
        List[float],
    ]:
        """Collapse dual-IP VMs to one hostname entry."""
        best: Dict[str, HostCollectResult] = {}
        alt_ips: Dict[str, List[str]] = {}

        for r in ok_results:
            key = _hostname_key(r.status)
            alt_ips.setdefault(key, [])
            if r.status.ip not in alt_ips[key]:
                alt_ips[key].append(r.status.ip)

            if key not in best:
                best[key] = r
                continue

            kept = best[key]
            preferred = _prefer_ip(kept.status.ip, r.status.ip)
            if preferred == r.status.ip:
                best[key] = r

        hosts: List[HostStatus] = []
        users: List[UserInfo] = []
        processes: Dict[str, List[ProcessInfo]] = {}
        host_processes: Dict[str, List[ProcessInfo]] = {}
        cpu_samples: List[float] = []
        mem_samples: List[float] = []
        seen_users: Dict[str, UserInfo] = {}

        for key, r in best.items():
            ips = sorted(alt_ips.get(key, [r.status.ip]), key=lambda ip: (0 if ip.startswith("192.168.15.") else 1, ip))
            primary = _prefer_ip(ips[0], r.status.ip) if ips else r.status.ip
            for ip in ips:
                primary = _prefer_ip(primary, ip)

            hostname = r.status.hostname or key
            detail = "ok" if len(ips) == 1 else f"ok ips={','.join(ips)}"
            hosts.append(
                HostStatus(
                    ip=primary,
                    hostname=hostname,
                    status="ok",
                    detail=detail,
                    onlineUsers=r.status.onlineUsers,
                    hostCpuUsage=round(r.host_cpu, 1),
                    hostMemoryUsage=round(r.host_mem, 1),
                )
            )
            cpu_samples.append(r.host_cpu)
            mem_samples.append(r.host_mem)

            for u in r.users:
                uid = f"{u.username}@{hostname}"
                user = UserInfo(
                    id=uid,
                    username=u.username,
                    vmName=hostname,
                    vmIp=primary,
                    cpuUsage=u.cpuUsage,
                    memoryUsage=u.memoryUsage,
                    loginTime=u.loginTime,
                )
                prev = seen_users.get(uid)
                if prev is None or (user.cpuUsage + user.memoryUsage) > (prev.cpuUsage + prev.memoryUsage):
                    seen_users[uid] = user

            processes.update(r.processes)
            if r.host_top:
                host_processes[hostname] = r.host_top
                host_processes[primary] = r.host_top
                for ip in ips:
                    host_processes[ip] = r.host_top

        users = list(seen_users.values())
        users.sort(key=lambda u: (u.cpuUsage + u.memoryUsage), reverse=True)
        hosts.sort(key=lambda h: (h.hostname or h.ip))
        return hosts, users, processes, host_processes, cpu_samples, mem_samples

    async def _collect_once(self) -> Snapshot:
        key_path = resolve_ssh_key(self.cfg)
        all_targets = expand_targets(self.cfg)
        logger.info("discovering %d targets", len(all_targets))
        reachable = await filter_reachable(all_targets, self.cfg)
        logger.info("%d hosts have SSH port open", len(reachable))

        sem = asyncio.Semaphore(self.cfg.concurrency)
        results = await asyncio.gather(
            *(collect_host(ip, self.cfg, key_path, sem) for ip in reachable)
        )

        ok_results = [r for r in results if r.status.status == "ok"]
        failed = [r.status for r in results if r.status.status != "ok"]

        ok_hosts, users, processes, host_processes, cpu_samples, mem_samples = self._dedupe_ok_hosts(
            ok_results
        )

        now = datetime.now().astimezone()
        avg_cpu = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0
        avg_mem = round(sum(mem_samples) / len(mem_samples), 1) if mem_samples else 0.0

        self._write_failed_hosts_log(failed, now)

        visible_hosts = ok_hosts + failed
        visible_hosts.sort(key=lambda h: (0 if h.status == "ok" else 1, h.hostname or h.ip, h.ip))

        stats = ClusterStats(
            onlineUsers=len(users),
            totalVMs=len(ok_hosts),
            totalCpuUsage=avg_cpu,
            totalMemoryUsage=avg_mem,
            reachableHosts=len(ok_hosts),
            failedHosts=len(failed),
            lastRefresh=now,
        )

        alerts = build_alerts(
            self.cfg,
            visible_hosts,
            users,
            self._prev_ok_keys,
            now,
        )
        self._notifier.persist_and_notify(self.cfg, alerts, now)

        # Update previous-ok set for next round "host lost" detection
        # tbn00–tbn18 excluded from 假死追踪
        self._prev_ok_keys = {
            (h.hostname or h.ip).lower()
            for h in ok_hosts
            if not is_tbn_host(h.hostname or h.ip)
        }

        return Snapshot(
            users=users,
            hosts=visible_hosts,
            stats=stats,
            processes=processes,
            hostProcesses=host_processes,
            alerts=alerts,
            meta=RefreshMeta(lastRefresh=now, refreshing=False, error=None),
        )

    def get_processes(self, username: str, vm_ip: Optional[str] = None) -> List[ProcessInfo]:
        if vm_ip:
            by_ip = self._snapshot.processes.get(f"{username}@{vm_ip}")
            if by_ip is not None:
                return by_ip
            for u in self._snapshot.users:
                if u.username == username and u.vmIp == vm_ip:
                    return self._snapshot.processes.get(f"{username}@{u.vmName}", [])
        for key, procs in self._snapshot.processes.items():
            if key.startswith(f"{username}@"):
                return procs
        return []

    def get_host_processes(
        self, hostname: Optional[str] = None, vm_ip: Optional[str] = None
    ) -> List[ProcessInfo]:
        hp = self._snapshot.hostProcesses
        if hostname and hostname in hp:
            return hp[hostname]
        if vm_ip and vm_ip in hp:
            return hp[vm_ip]
        if hostname:
            for h in self._snapshot.hosts:
                if (h.hostname or "").lower() == hostname.lower():
                    return hp.get(h.hostname or "", []) or hp.get(h.ip, [])
        return []
