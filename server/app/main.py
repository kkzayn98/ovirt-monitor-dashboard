from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .collector import CollectorService
from .models import Alert, ClusterStats, HostStatus, ProcessInfo, RefreshMeta, UserInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("asyncssh").setLevel(logging.WARNING)

collector = CollectorService()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await collector.start()
    yield
    await collector.stop()


app = FastAPI(title="oVirt User Monitor API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"ok": True, "meta": collector.snapshot.meta}


@app.get("/api/stats", response_model=ClusterStats)
async def stats() -> ClusterStats:
    return collector.snapshot.stats


@app.get("/api/users", response_model=List[UserInfo])
async def users() -> List[UserInfo]:
    return collector.snapshot.users


@app.get("/api/users/{username}/processes", response_model=List[ProcessInfo])
async def user_processes(
    username: str,
    vmIp: Optional[str] = Query(default=None),
) -> List[ProcessInfo]:
    procs = collector.get_processes(username, vmIp)
    if not procs and not any(u.username == username for u in collector.snapshot.users):
        raise HTTPException(status_code=404, detail="user not found in last snapshot")
    return procs


@app.get("/api/hosts/{hostname}/processes", response_model=List[ProcessInfo])
async def host_processes(
    hostname: str,
    vmIp: Optional[str] = Query(default=None),
) -> List[ProcessInfo]:
    procs = collector.get_host_processes(hostname=hostname, vm_ip=vmIp)
    if not procs:
        # Still ok to return empty if host known; 404 only if unknown
        known = any(
            (h.hostname or "").lower() == hostname.lower() or h.ip == hostname or h.ip == (vmIp or "")
            for h in collector.snapshot.hosts
            if h.status == "ok"
        )
        if not known:
            raise HTTPException(status_code=404, detail="host not found in last snapshot")
    return procs


@app.get("/api/hosts", response_model=List[HostStatus])
async def hosts() -> List[HostStatus]:
    return collector.snapshot.hosts


@app.get("/api/alerts", response_model=List[Alert])
async def alerts() -> List[Alert]:
    return collector.snapshot.alerts


@app.get("/api/meta", response_model=RefreshMeta)
async def meta() -> RefreshMeta:
    return collector.snapshot.meta


@app.post("/api/refresh")
async def refresh():
    """Kick off a full recollect without blocking the HTTP response."""
    if not collector.snapshot.meta.refreshing:
        asyncio.create_task(collector.refresh())
    return {"ok": True, "meta": collector.snapshot.meta, "stats": collector.snapshot.stats}