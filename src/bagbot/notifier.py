"""Notifier base + 4 adapters, all with Chinese templates.

Adapters (each can be enabled independently):
  - Generic Webhook (Slack / Discord / DingTalk style)
  - Feishu / Lark (with optional signed timestamp)
  - WeChat Work (corp app push, text only)
  - Email (SMTP)

All adapters are best-effort: a failure to notify never blocks the daemon.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from .config import NotifierCfg

log = logging.getLogger("bagbot.notifier")


# ── Event types ───────────────────────────────────────────────────────────

@dataclass
class NotifyEvent:
    """An event to broadcast.

    `level` ∈ {"info","warn","error","success"}.
    `kind` is a short machine tag (e.g. "key_claimed").
    """
    level: str
    kind: str
    title: str       # short headline
    summary: str     # 1-2 sentence narrative
    payload: Dict[str, Any]


# ── Locale helpers ────────────────────────────────────────────────────────

_ZH_TEMPLATES = {
    "key_claimed": "🟢 成功领取新 key：headroom ${headroom:.2f}",
    "key_topped_up": "🔵 已为 key 充值 ${amount:.2f}",
    "key_rotated": "🟡 已轮换 key（{reason}）",
    "key_deleted": "🔴 已停用 key（{reason}）",
    "balance_low": "⚠️ 未领取余额偏低：${unclaimed:.2f}（阈值 ${threshold:.2f}）",
    "burn_high": "🔥 燃烧速度异常：${rate:.2f}/h（阈值 ${threshold:.2f}/h）",
    "tick": "📊 状态：余额 ${balance:.2f} · key 已用 {used:.0%} · 燃烧 ${rate:.2f}/h",
    "startup": "🪐 BagBot 已启动（{label}）",
    "shutdown": "🛑 BagBot 已停止",
    "error": "❌ 错误：{msg}",
}

_EN_TEMPLATES = {
    "key_claimed": "🟢 Claimed new key: headroom ${headroom:.2f}",
    "key_topped_up": "🔵 Topped up key by ${amount:.2f}",
    "key_rotated": "🟡 Rotated key ({reason})",
    "key_deleted": "🔴 Deleted key ({reason})",
    "balance_low": "⚠️ Unclaimed balance low: ${unclaimed:.2f} (threshold ${threshold:.2f})",
    "burn_high": "🔥 Burn rate abnormal: ${rate:.2f}/h (threshold ${threshold:.2f}/h)",
    "tick": "📊 Balance ${balance:.2f} · key used {used:.0%} · burn ${rate:.2f}/h",
    "startup": "🪐 BagBot started ({label})",
    "shutdown": "🛑 BagBot stopped",
    "error": "❌ Error: {msg}",
}


def render_message(lang: str, kind: str, **fmt: Any) -> str:
    tpl = (_ZH_TEMPLATES if lang.startswith("zh") else _EN_TEMPLATES).get(kind, kind)
    try:
        return tpl.format(**fmt)
    except KeyError:
        return tpl


# ── Base adapter ──────────────────────────────────────────────────────────

class BaseAdapter:
    name = "base"

    def __init__(self, cfg: NotifierCfg, lang: str):
        self.cfg = cfg
        self.lang = lang

    async def send(self, ev: NotifyEvent) -> None:
        raise NotImplementedError

    def render(self, ev: NotifyEvent) -> str:
        return render_message(self.lang, ev.kind, **ev.payload)


# ── Webhook (generic) ─────────────────────────────────────────────────────

class WebhookAdapter(BaseAdapter):
    name = "webhook"

    async def send(self, ev: NotifyEvent) -> None:
        if not self.cfg.webhook_url:
            return
        body = {
            "level": ev.level,
            "kind": ev.kind,
            "title": ev.title,
            "summary": ev.summary,
            "text": self.render(ev),
            "payload": ev.payload,
            "ts": int(time.time()),
        }
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self.cfg.webhook_url, json=body)
            r.raise_for_status()
        log.debug("webhook delivered: %s", ev.kind)


# ── Feishu / Lark ─────────────────────────────────────────────────────────

class FeishuAdapter(BaseAdapter):
    name = "feishu"

    @staticmethod
    def _sign(secret: str, ts: int) -> str:
        s = f"{ts}\n{secret}".encode()
        h = hmac.new(s, digestmod=hashlib.sha256).digest()
        return base64.b64encode(h).decode()

    async def send(self, ev: NotifyEvent) -> None:
        if not self.cfg.feishu_webhook_url:
            return
        body: Dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": ev.title},
                    "template": {
                        "info": "blue", "success": "green",
                        "warn": "orange", "error": "red",
                    }.get(ev.level, "blue"),
                },
                "elements": [
                    {"tag": "markdown", "content": self.render(ev)},
                    {"tag": "note", "elements": [
                        {"tag": "plain_text",
                         "content": f"BagBot · {ev.kind} · {time.strftime('%Y-%m-%d %H:%M:%S')}"}
                    ]},
                ],
            },
        }
        if self.cfg.feishu_secret:
            ts = int(time.time())
            body["timestamp"] = str(ts)
            body["sign"] = self._sign(self.cfg.feishu_secret, ts)
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self.cfg.feishu_webhook_url, json=body)
            r.raise_for_status()
        log.debug("feishu delivered: %s", ev.kind)


# ── WeChat Work (corp app, text only) ─────────────────────────────────────

class WeChatAdapter(BaseAdapter):
    name = "wechat"

    async def send(self, ev: NotifyEvent) -> None:
        if not (self.cfg.wechat_corp_id and self.cfg.wechat_agent_id and self.cfg.wechat_secret):
            return
        # 1. fetch access_token
        token_url = (
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            f"?corpid={self.cfg.wechat_corp_id}&corpsecret={self.cfg.wechat_secret}"
        )
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(token_url)
            data = r.json()
        if data.get("errcode") != 0:
            log.warning("wechat gettoken failed: %s", data)
            return
        access_token = data["access_token"]
        # 2. send text
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        body = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": int(self.cfg.wechat_agent_id),
            "text": {"content": f"{ev.title}\n{self.render(ev)}"},
        }
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(send_url, json=body)
            data = r.json()
        if data.get("errcode") != 0:
            log.warning("wechat send failed: %s", data)
        else:
            log.debug("wechat delivered: %s", ev.kind)


# ── Email ─────────────────────────────────────────────────────────────────

class EmailAdapter(BaseAdapter):
    name = "email"

    def _send_sync(self, ev: NotifyEvent) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"[BagBot] {ev.title}"
        msg["From"] = self.cfg.email_from
        msg["To"] = self.cfg.email_to
        msg.set_content(self.render(ev))
        if self.cfg.smtp_port == 465:
            with smtplib.SMTP_SSL(self.cfg.smtp_host, self.cfg.smtp_port) as s:
                s.login(self.cfg.smtp_username, self.cfg.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port) as s:
                s.starttls()
                s.login(self.cfg.smtp_username, self.cfg.smtp_password)
                s.send_message(msg)

    async def send(self, ev: NotifyEvent) -> None:
        if not (self.cfg.smtp_host and self.cfg.email_from and self.cfg.email_to):
            return
        try:
            await asyncio.to_thread(self._send_sync, ev)
            log.debug("email delivered: %s", ev.kind)
        except Exception as e:  # never crash daemon on email failure
            log.warning("email send failed: %s", e)


# ── Composite dispatcher ──────────────────────────────────────────────────

class Notifier:
    """Fan out an event to all enabled adapters.

    Failures are isolated; we log and continue.
    """

    def __init__(self, cfg: NotifierCfg, lang: str = "zh-CN"):
        self.adapters: list[BaseAdapter] = []
        if cfg.webhook_url:
            self.adapters.append(WebhookAdapter(cfg, lang))
        if cfg.feishu_webhook_url:
            self.adapters.append(FeishuAdapter(cfg, lang))
        if cfg.wechat_corp_id and cfg.wechat_agent_id and cfg.wechat_secret:
            self.adapters.append(WeChatAdapter(cfg, lang))
        if cfg.smtp_host and cfg.email_from and cfg.email_to:
            self.adapters.append(EmailAdapter(cfg, lang))

    async def notify(
        self,
        level: str,
        kind: str,
        title: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.adapters:
            return
        ev = NotifyEvent(
            level=level, kind=kind, title=title, summary=summary,
            payload=payload or {},
        )
        results = await asyncio.gather(
            *(a.send(ev) for a in self.adapters), return_exceptions=True
        )
        for a, r in zip(self.adapters, results):
            if isinstance(r, Exception):
                log.warning("notifier %s failed on %s: %s", a.name, kind, r)
