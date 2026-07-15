from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .collector import CollectorService
from .models import Alert, ClusterStats, HostStatus, ProcessInfo, RefreshMeta, UserInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("asyncssh").setLevel(logging.WARNING)

collector = CollectorService()

# Built frontend: repo/dist  (npm run build)
DIST_DIR = Path(__file__).resolve().parents[2] / "dist"


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


# Serve production UI from the same origin as /api (avoids Vite proxy 502)
if DIST_DIR.is_dir():
    assets = DIST_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(DIST_DIR.resolve())
        except ValueError:
            return FileResponse(DIST_DIR / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
