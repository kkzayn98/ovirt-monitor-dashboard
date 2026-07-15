from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import ROOT, AppConfig
from .models import Alert, HostStatus, UserInfo

logger = logging.getLogger(__name__)

# tbn00–tbn18: RainaSynth 分布式节点 — 跳过假死/CPU/内存告警（短时 100% 属正常）
_TBN_HOST_RE = re.compile(r"^tbn(0?[0-9]|1[0-8])$", re.IGNORECASE)


def is_tbn_host(name: str) -> bool:
    short = (name or "").strip().split(".", 1)[0].lower()
    return bool(_TBN_HOST_RE.match(short))


def _top_users_on_host(users: List[UserInfo], hostname: str, limit: int = 3) -> List[str]:
    rows = [u for u in users if u.vmName.lower() == hostname.lower()]
    rows.sort(key=lambda u: (u.memoryUsage + u.cpuUsage), reverse=True)
    return [u.username for u in rows[:limit]]


def _level_for(value: float, warn: float, crit: float) -> Optional[str]:
    if value >= crit:
        return "critical"
    if value >= warn:
        return "warning"
    return None


def build_alerts(
    cfg: AppConfig,
    hosts: List[HostStatus],
    users: List[UserInfo],
    prev_ok_keys: Set[str],
    now: datetime,
) -> List[Alert]:
    a = cfg.alerts
    alerts: List[Alert] = []

    ok_hosts = [h for h in hosts if h.status == "ok"]
    current_ok = {(h.hostname or h.ip).lower() for h in ok_hosts}

    for h in ok_hosts:
        hostname = h.hostname or h.ip
        # tbn00–tbn18: RainaSynth 分布式节点，短时打满 CPU 属正常，跳过主机级告警
        if is_tbn_host(hostname):
            continue
        suspects = _top_users_on_host(users, hostname)
        suspect_txt = "、".join(suspects) if suspects else "（无明显登录用户）"

        cpu_lv = _level_for(h.hostCpuUsage, a.cpu_warn, a.cpu_crit)
        if cpu_lv:
            alerts.append(
                Alert(
                    id=f"host_cpu:{hostname}",
                    level=cpu_lv,  # type: ignore[arg-type]
                    kind="host_cpu",
                    hostname=hostname,
                    ip=h.ip,
                    message=(
                        f"{hostname} CPU {h.hostCpuUsage:.1f}% "
                        f"（阈值 {a.cpu_warn:g}/{a.cpu_crit:g}%），"
                        f"建议 IT 提醒：{suspect_txt}"
                    ),
                    suspectedUsers=suspects,
                    value=h.hostCpuUsage,
                    threshold=a.cpu_crit if cpu_lv == "critical" else a.cpu_warn,
                    createdAt=now,
                )
            )

        mem_lv = _level_for(h.hostMemoryUsage, a.mem_warn, a.mem_crit)
        if mem_lv:
            alerts.append(
                Alert(
                    id=f"host_mem:{hostname}",
                    level=mem_lv,  # type: ignore[arg-type]
                    kind="host_mem",
                    hostname=hostname,
                    ip=h.ip,
                    message=(
                        f"{hostname} 内存 {h.hostMemoryUsage:.1f}% "
                        f"（阈值 {a.mem_warn:g}/{a.mem_crit:g}%），"
                        f"有 OOM/SSH 假死风险，建议 IT 提醒：{suspect_txt}"
                    ),
                    suspectedUsers=suspects,
                    value=h.hostMemoryUsage,
                    threshold=a.mem_crit if mem_lv == "critical" else a.mem_warn,
                    createdAt=now,
                )
            )

    # Users driving host pressure (even if host average not yet critical)
    for u in users:
        if is_tbn_host(u.vmName):
            continue
        if u.cpuUsage >= a.user_cpu_warn:
            alerts.append(
                Alert(
                    id=f"user_cpu:{u.username}@{u.vmName}",
                    level="warning" if u.cpuUsage < a.cpu_crit else "critical",  # type: ignore[arg-type]
                    kind="user_cpu",
                    hostname=u.vmName,
                    ip=u.vmIp,
                    message=(
                        f"用户 {u.username} 在 {u.vmName} 占用 CPU {u.cpuUsage:.1f}%（主机整体比例），"
                        f"请 IT 联系该用户清理/限流"
                    ),
                    suspectedUsers=[u.username],
                    value=u.cpuUsage,
                    threshold=a.user_cpu_warn,
                    createdAt=now,
                )
            )
        if u.memoryUsage >= a.user_mem_warn:
            alerts.append(
                Alert(
                    id=f"user_mem:{u.username}@{u.vmName}",
                    level="warning" if u.memoryUsage < a.mem_crit else "critical",  # type: ignore[arg-type]
                    kind="user_mem",
                    hostname=u.vmName,
                    ip=u.vmIp,
                    message=(
                        f"用户 {u.username} 在 {u.vmName} 占用内存 {u.memoryUsage:.1f}%（主机整体比例），"
                        f"请 IT 联系该用户，防止 OOM"
                    ),
                    suspectedUsers=[u.username],
                    value=u.memoryUsage,
                    threshold=a.user_mem_warn,
                    createdAt=now,
                )
            )

    # Previously reachable hosts that disappeared — possible hang/OOM/kernel issue
    # Skip tbn00–tbn18 (no 「假死」校验)
    if prev_ok_keys:
        lost = prev_ok_keys - current_ok
        failed_by_name = {
            (h.hostname or h.ip).lower(): h
            for h in hosts
            if h.status != "ok"
        }
        for key in sorted(lost):
            if is_tbn_host(key):
                continue
            h = failed_by_name.get(key)
            ip = h.ip if h else key
            status = h.status if h else "unreachable"
            alerts.append(
                Alert(
                    id=f"host_lost:{key}",
                    level="critical",
                    kind="host_lost",
                    hostname=key,
                    ip=ip,
                    message=(
                        f"主机 {key} 上一轮可采、本轮 SSH 失败（{status}），"
                        f"可能已 OOM/假死/内核异常，请 IT 立刻登控制台（SPICE/VNC）检查"
                    ),
                    suspectedUsers=[],
                    value=100.0,
                    threshold=0.0,
                    createdAt=now,
                )
            )

    # Prefer critical first, then by value
    level_rank = {"critical": 0, "warning": 1}
    alerts.sort(key=lambda x: (level_rank.get(x.level, 9), -x.value, x.hostname))
    return alerts


class AlertNotifier:
    """Write alerts log + optional webhook with cooldown to avoid spam."""

    def __init__(self) -> None:
        self._last_sent: Dict[str, float] = {}

    def _log_path(self, cfg: AppConfig) -> Path:
        path = Path(cfg.alerts.alerts_log)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def persist_and_notify(self, cfg: AppConfig, alerts: List[Alert], now: datetime) -> None:
        path = self._log_path(cfg)
        lines = [
            f"# Alerts refreshed at {now.isoformat()}",
            f"# critical={sum(1 for a in alerts if a.level=='critical')} "
            f"warning={sum(1 for a in alerts if a.level=='warning')}",
            "",
        ]
        for al in alerts:
            users = ",".join(al.suspectedUsers) if al.suspectedUsers else "-"
            lines.append(
                f"{al.createdAt.isoformat()}\t{al.level}\t{al.kind}\t{al.hostname}\t{al.ip}\t"
                f"{al.value}\t{users}\t{al.message}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Compact actionable IT brief
        brief = path.with_name("alerts_it_brief.txt")
        brief_lines = [
            f"Raina 集群资源预警 · {now.strftime('%Y-%m-%d %H:%M:%S')}",
            "请 IT 联系下列用户尽快释放资源 / 排查主机：",
            "",
        ]
        for al in alerts:
            if al.level != "critical" and al.kind.startswith("user_"):
                continue
            who = "、".join(al.suspectedUsers) if al.suspectedUsers else "未知用户"
            brief_lines.append(f"- [{al.level}] {al.hostname} ({al.ip}): {al.message}")
            if al.suspectedUsers:
                brief_lines.append(f"  → 联系用户: {who}")
        brief.write_text("\n".join(brief_lines) + "\n", encoding="utf-8")

        to_notify = [al for al in alerts if al.level == "critical"]
        if not to_notify:
            to_notify = alerts[:5]

        webhook = (cfg.alerts.webhook_url or "").strip()
        if not webhook or not to_notify:
            return

        cooldown = cfg.alerts.notify_cooldown_seconds
        now_ts = time.time()
        fresh: List[Alert] = []
        for al in to_notify:
            last = self._last_sent.get(al.id, 0)
            if now_ts - last >= cooldown:
                fresh.append(al)
                self._last_sent[al.id] = now_ts

        if not fresh:
            return

        text = self._format_webhook_text(fresh, now)
        try:
            # sync HTTP — caller should offload to a thread if on asyncio loop
            self._post_webhook(webhook, text, secret=cfg.alerts.dingtalk_secret or "")
            logger.info("sent %d alert(s) to webhook", len(fresh))
        except Exception:  # noqa: BLE001
            logger.exception("webhook notify failed")

    async def persist_and_notify_async(
        self, cfg: AppConfig, alerts: List[Alert], now: datetime
    ) -> None:
        """Write logs synchronously; post webhook off the event loop."""
        await asyncio.to_thread(self.persist_and_notify, cfg, alerts, now)

    @staticmethod
    def _format_webhook_text(alerts: List[Alert], now: datetime) -> str:
        """DingTalk: machine + host CPU/MEM + users."""
        by_host: Dict[str, dict] = {}
        for al in alerts[:20]:
            host = al.hostname or al.ip or "?"
            row = by_host.setdefault(host, {"cpu": None, "mem": None, "users": []})
            if al.kind == "host_cpu":
                row["cpu"] = al.value
            elif al.kind == "host_mem":
                row["mem"] = al.value
            elif al.kind == "user_cpu" and row["cpu"] is None:
                row["cpu"] = al.value  # fallback when only user alert
            elif al.kind == "user_mem" and row["mem"] is None:
                row["mem"] = al.value
            for name in al.suspectedUsers or []:
                if name and name not in row["users"]:
                    row["users"].append(name)

        lines = [f"【Raina 预警】{now.strftime('%H:%M:%S')}"]
        for host, row in by_host.items():
            parts: List[str] = []
            if row["cpu"] is not None:
                parts.append(f"CPU {row['cpu']:.0f}%")
            if row["mem"] is not None:
                parts.append(f"MEM {row['mem']:.0f}%")
            usage = " ".join(parts) if parts else "资源告急"
            who = "、".join(row["users"]) if row["users"] else "-"
            lines.append(f"{host} {usage} → {who}")
        return "\n".join(lines)

    @staticmethod
    def _sign_dingtalk_url(url: str, secret: str) -> str:
        """Append timestamp & sign for DingTalk custom robot (加签)."""
        secret = (secret or "").strip()
        if not secret:
            return url
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        sep = "&" if ("?" in url) else "?"
        return f"{url}{sep}timestamp={timestamp}&sign={sign}"

    @staticmethod
    def _post_webhook(url: str, text: str, secret: str = "") -> None:
        """POST text message; DingTalk first, then Feishu/WeCom fallbacks."""
        signed_url = AlertNotifier._sign_dingtalk_url(url, secret)
        payloads = [
            {"msgtype": "text", "text": {"content": text}},
            {"msg_type": "text", "content": {"text": text}},
            {"text": text},
        ]
        last_err: Optional[Exception] = None
        last_body = ""
        for body in payloads:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                signed_url,
                data=data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    last_body = raw
                    if 200 <= resp.status < 300:
                        # DingTalk returns HTTP 200 even on biz error
                        try:
                            parsed = json.loads(raw) if raw else {}
                        except json.JSONDecodeError:
                            return
                        errcode = parsed.get("errcode", 0)
                        if errcode in (0, None, "0"):
                            return
                        last_err = RuntimeError(f"webhook biz error: {raw}")
                        signed_url = AlertNotifier._sign_dingtalk_url(url, secret)
                        continue
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                signed_url = AlertNotifier._sign_dingtalk_url(url, secret)
                continue
        if last_err:
            raise last_err
        raise RuntimeError(f"webhook failed: {last_body}")
