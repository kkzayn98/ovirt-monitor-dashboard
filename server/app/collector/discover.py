from __future__ import annotations

import asyncio
import ipaddress
from typing import Iterable, List, Set

from ..config import AppConfig


def expand_targets(cfg: AppConfig) -> List[str]:
    seen: Set[str] = set()
    exclude = set(cfg.exclude_ips)
    result: List[str] = []

    for host in cfg.hosts:
        host = host.strip()
        if not host or host in exclude or host in seen:
            continue
        seen.add(host)
        result.append(host)

    for cidr in cfg.cidrs:
        network = ipaddress.ip_network(cidr, strict=False)
        for ip in network.hosts():
            s = str(ip)
            if s in exclude or s in seen:
                continue
            seen.add(s)
            result.append(s)

    return result


async def probe_ssh_port(host: str, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, 22), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def filter_reachable(hosts: Iterable[str], cfg: AppConfig) -> List[str]:
    hosts_list = list(hosts)
    sem = asyncio.Semaphore(cfg.concurrency * 2)

    async def check(h: str) -> str | None:
        async with sem:
            ok = await probe_ssh_port(h, cfg.port_probe_timeout)
            return h if ok else None

    results = await asyncio.gather(*(check(h) for h in hosts_list))
    return [h for h in results if h]