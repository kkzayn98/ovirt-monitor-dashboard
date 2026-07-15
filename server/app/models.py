from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    pid: str
    name: str
    user: str
    cpuUsage: float
    memoryUsage: float
    startTime: datetime


class UserInfo(BaseModel):
    id: str
    username: str
    vmName: str
    vmIp: str
    cpuUsage: float
    memoryUsage: float
    loginTime: datetime


class ClusterStats(BaseModel):
    onlineUsers: int
    totalVMs: int
    totalCpuUsage: float
    totalMemoryUsage: float
    reachableHosts: int = 0
    failedHosts: int = 0
    lastRefresh: Optional[datetime] = None


class HostStatus(BaseModel):
    ip: str
    hostname: Optional[str] = None
    status: Literal["ok", "unreachable", "auth_failed", "error"]
    detail: str = ""
    onlineUsers: int = 0
    hostCpuUsage: float = 0.0
    hostMemoryUsage: float = 0.0


class Alert(BaseModel):
    id: str
    level: Literal["warning", "critical"]
    kind: Literal["host_cpu", "host_mem", "host_lost", "user_cpu", "user_mem"]
    hostname: str
    ip: str
    message: str
    suspectedUsers: List[str] = Field(default_factory=list)
    value: float = 0.0
    threshold: float = 0.0
    createdAt: datetime


class RefreshMeta(BaseModel):
    lastRefresh: Optional[datetime] = None
    refreshing: bool = False
    error: Optional[str] = None


class Snapshot(BaseModel):
    users: List[UserInfo] = Field(default_factory=list)
    hosts: List[HostStatus] = Field(default_factory=list)
    stats: ClusterStats
    processes: dict[str, List[ProcessInfo]] = Field(default_factory=dict)
    hostProcesses: dict[str, List[ProcessInfo]] = Field(default_factory=dict)
    alerts: List[Alert] = Field(default_factory=list)
    meta: RefreshMeta = Field(default_factory=RefreshMeta)