from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"
SECRETS_FILE = ROOT / "secrets.yaml"


class AlertSettings(BaseModel):
    cpu_warn: float = 80
    cpu_crit: float = 90
    mem_warn: float = 85
    mem_crit: float = 92
    user_cpu_warn: float = 90
    user_mem_warn: float = 90
    alerts_log: str = "logs/alerts.log"
    webhook_url: str = ""
    # DingTalk custom robot SEC for signed webhook (optional)
    dingtalk_secret: str = ""
    notify_cooldown_seconds: int = 1800


class AuthProfile(BaseModel):
    """Per-host-group SSH credentials (e.g. tbn00-tbn18 use root+password)."""

    name: str = "default"
    # Match connection target OR resolved short hostname
    hostname_regex: str = ""
    ssh_user: str = "root"
    # Prefer secret_key from secrets.yaml; plaintext ssh_password is fallback
    secret_key: str = ""
    ssh_password: str = ""
    use_key: bool = False


class AppConfig(BaseModel):
    ssh_user: str = "kangzijin"
    ssh_key: str = "/home/kangzijin/.ssh/id_ed25519"
    cidrs: List[str] = Field(default_factory=lambda: ["192.168.15.0/24", "192.168.10.0/24"])
    hosts: List[str] = Field(default_factory=list)
    concurrency: int = 32
    connect_timeout: float = 5.0
    command_timeout: float = 10.0
    port_probe_timeout: float = 1.5
    refresh_interval_seconds: int = 120
    exclude_ips: List[str] = Field(default_factory=list)
    failed_hosts_log: str = "logs/ssh_failed_hosts.log"
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    auth_profiles: List[AuthProfile] = Field(default_factory=list)


@dataclass
class ResolvedAuth:
    username: str
    password: Optional[str] = None
    use_key: bool = True
    profile_name: str = "default"


def _load_secrets() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    return yaml.safe_load(SECRETS_FILE.read_text(encoding="utf-8")) or {}


@lru_cache()
def get_config() -> AppConfig:
    path = DEFAULT_CONFIG
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = AppConfig(**raw)
    else:
        cfg = AppConfig()

    secrets = _load_secrets()
    # Overlay DingTalk / webhook from secrets (do not commit)
    if secrets.get("dingtalk_webhook_url"):
        cfg.alerts.webhook_url = str(secrets["dingtalk_webhook_url"]).strip()
    if secrets.get("dingtalk_secret"):
        cfg.alerts.dingtalk_secret = str(secrets["dingtalk_secret"]).strip()
    if secrets.get("webhook_url") and not cfg.alerts.webhook_url:
        cfg.alerts.webhook_url = str(secrets["webhook_url"]).strip()
    return cfg


def resolve_ssh_key(cfg: AppConfig) -> Path:
    key = Path(cfg.ssh_key).expanduser()
    if key.is_file():
        return key
    fallbacks = [
        Path("/home/kangzijin/.ssh/id_ed25519"),
        Path("/root/.ssh/id_ed25519"),
        Path.home() / ".ssh" / "id_ed25519",
    ]
    for candidate in fallbacks:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"SSH private key not found: {cfg.ssh_key}")


def resolve_auth(target: str, cfg: Optional[AppConfig] = None) -> ResolvedAuth:
    """Pick SSH auth for a target hostname/IP based on auth_profiles."""
    cfg = cfg or get_config()
    secrets = _load_secrets()
    name = target.strip().split(".", 1)[0].lower()

    for profile in cfg.auth_profiles:
        if not profile.hostname_regex:
            continue
        try:
            if not re.search(profile.hostname_regex, name, re.IGNORECASE):
                # Also try full target (e.g. if only IP is known — pattern won't match IP)
                if not re.search(profile.hostname_regex, target, re.IGNORECASE):
                    continue
        except re.error:
            continue

        password = profile.ssh_password
        if profile.secret_key and profile.secret_key in secrets:
            password = str(secrets[profile.secret_key])
        return ResolvedAuth(
            username=profile.ssh_user,
            password=password or None,
            use_key=profile.use_key,
            profile_name=profile.name,
        )

    return ResolvedAuth(username=cfg.ssh_user, password=None, use_key=True, profile_name="default")
