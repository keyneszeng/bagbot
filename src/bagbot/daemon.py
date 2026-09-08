"""Core BagBot daemon — the 7×24 event loop.

Lifecycle per tick (every POLL_INTERVAL_SEC seconds), against the **live
Orbio gateway API** (5 tools, verified 2026-09-08):

  1.  Read balance (orbio_get_balance)     — balance IS the quota
  2.  Read key status (orbio_get_key_status) — per-account, no args
  3.  Compute spend rate from balance history
  4.  Decide (policy.decide): CREATE / REVOKE / DELETE / ALERT / NOTHING
  5.  Execute + persist to SQLite + notify
  6.  Sleep

Gateway model: the key never holds credit — the gateway draws on the
account balance request-by-request.  So there is no "top-up", and
"rotation" is just ``orbio_create_key`` again (old key retired atomically,
``replaced: true``).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass

from .config import Settings
from .notifier import Notifier
from .orbio_mcp import (
    Balance,
    KeyStatus,
    OrbioMCPClient,
    OrbioMCPError,
)
from .policy import Action, PolicyConfig, Snapshot, decide
from .state import KeyRecord, StateStore

log = logging.getLogger("bagbot.daemon")


@dataclass
class TickReport:
    ts: float
    balance: Balance
    status: KeyStatus | None
    action: Action
    reason: str


class BagBot:
    def __init__(self, settings: Settings):
        self.cfg = settings
        self.policy = PolicyConfig(
            low_balance_usd=settings.low_balance_usd,
            rotate_max_age_hours=settings.rotate_max_age_hours,
            leak_rate_usd_per_hour=settings.rotate_burst_usd_per_hour,
        )
        self.state = StateStore(settings.state_db_path)
        self.notifier = Notifier(settings.notifier, lang=settings.language)
        # Defer MCP client creation when no token is configured: allows
        # zero-config runs (tests, `scripts/demo_e2e.py`) to construct the
        # object; a real tick raises a clear OrbioMCPError instead of
        # failing at import time.
        self.mcp: OrbioMCPClient | None = (
            OrbioMCPClient(
                endpoint=settings.orbio_mcp_url, token=settings.orbio_mcp_token
            )
            if settings.orbio_mcp_token
            else None
        )
        if self.mcp is None:
            log.warning(
                "ORBIO_MCP_TOKEN is empty — constructed without an MCP client. "
                "Set the token before running real ticks."
            )
        self._stop_event = asyncio.Event()
        self._last_tick: TickReport | None = None
        self._last_status: KeyStatus | None = None
        # Burn-rate sampling: previous spendable balance + timestamp.
        self._last_balance_usd: float | None = None
        self._last_balance_ts: float = 0.0

    def require_mcp(self) -> OrbioMCPClient:
        """Return the MCP client, raising a clear error if absent.

        Callers (daemon tick, dashboard endpoints, CLI commands) that are
        about to hit the network use this instead of touching ``self.mcp``
        directly, so a zero-config object fails with an actionable message
        rather than ``AttributeError: 'NoneType'``.
        """
        if self.mcp is None:
            raise OrbioMCPError(
                "mcp",
                "ORBIO_MCP_TOKEN is empty — set it in .env to talk to Orbio MCP.",
            )
        return self.mcp

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        await self.state.init()
        await self.notifier.notify(
            "info", "startup", "BagBot 已启动",
            f"钱包 {self.cfg.wallet_label} · 钱包地址 {self.cfg.orbio_wallet[:10]}…",
            {"label": self.cfg.wallet_label},
        )
        log.info("BagBot started (wallet=%s label=%s)",
                 self.cfg.orbio_wallet, self.cfg.wallet_label)

    async def stop(self) -> None:
        await self.notifier.notify(
            "info", "shutdown", "BagBot 已停止", "正常退出", {}
        )
        log.info("BagBot stopped")
        self._stop_event.set()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        """Main loop."""
        await self.start()
        try:
            while not self._stop_event.is_set():
                try:
                    await self.tick()
                except OrbioMCPError as e:
                    log.error("MCP error during tick: %s", e)
                    await self.state.log_event("error", "mcp_error", str(e), {"tool": e.tool})
                    await self.notifier.notify(
                        "error", "error", "MCP 错误",
                        str(e), {"tool": e.tool},
                    )
                except Exception as e:  # noqa: BLE001
                    log.exception("unexpected tick failure: %s", e)
                    await self.state.log_event(
                        "error", "tick_failure", str(e), {}
                    )
                # Interruptible sleep.
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.cfg.poll_interval_sec,
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.stop()

    # ── One tick ─────────────────────────────────────────────────────

    async def tick(self) -> TickReport:
        mcp = self.require_mcp()
        balance = await mcp.get_balance()
        await self.state.record_balance(
            balance.accrued_usd, balance.claimed_usd, balance.unclaimed_usd
        )

        # Key status is per-account in the live API (takes no arguments).
        try:
            status = await mcp.get_key_status()
        except OrbioMCPError as e:
            log.warning("could not read key status: %s", e)
            status = None

        has_key = bool(status and status.has_key)
        burn_rate = self._compute_burn_rate(balance.unclaimed_usd)

        current = await self.state.current_key()
        key_age_hours = (
            (time.time() - current.created_at) / 3600.0 if current else 0.0
        )

        snap = Snapshot(
            has_key=has_key,
            key_prefix=status.prefix if status else None,
            key_age_hours=key_age_hours,
            spend_rate_usd_per_hour=burn_rate,
            balance_usd=balance.unclaimed_usd,
            accrued_usd=balance.accrued_usd,
            last_used_at=status.last_used_at if status else None,
            has_legacy_key=bool(status and status.legacy),
        )

        action, reason = decide(snap, self.policy)
        log.info("tick: bal=$%.2f has_key=%s action=%s reason=%s",
                 balance.unclaimed_usd, has_key, action.value, reason)

        await self._execute(action, reason, current, balance, status, mcp)
        report = TickReport(
            ts=time.time(), balance=balance, status=status,
            action=action, reason=reason,
        )
        self._last_tick = report
        if status is not None:
            self._last_status = status
        return report

    # ── Helpers ──────────────────────────────────────────────────────

    def _compute_burn_rate(self, balance_usd: float) -> float:
        """Estimate USD/hour of spend from consecutive balance samples.

        The gateway draws the account balance, so the balance curve IS the
        spend curve.  Returns 0.0 until there are two samples; balance
        increases (accruals) count as zero burn.
        """
        now = time.time()
        prev, prev_ts = self._last_balance_usd, self._last_balance_ts
        self._last_balance_usd = balance_usd
        self._last_balance_ts = now
        if prev is None or prev_ts <= 0:
            return 0.0
        dt = now - prev_ts
        if dt <= 0:
            return 0.0
        delta = prev - balance_usd  # positive = spending
        if delta <= 0:
            return 0.0
        return (delta / dt) * 3600.0

    async def _execute(
        self,
        action: Action,
        reason: str,
        current: KeyRecord | None,
        balance: Balance,
        status: KeyStatus | None,
        mcp: OrbioMCPClient,
    ) -> None:
        if action == Action.NOTHING:
            return

        # ALERT can fire alongside a healthy key — it must run before the
        # "no current key" guard.
        if action == Action.ALERT:
            await self.state.log_event("warn", "balance_low", reason, {
                "balance_usd": balance.unclaimed_usd,
            })
            await self.notifier.notify(
                "warn", "balance_low", "可花余额偏低", reason,
                {"balance": balance.unclaimed_usd,
                 "threshold": self.policy.low_balance_usd},
            )
            return

        if action == Action.CREATE:
            key = await mcp.create_key(label=self.cfg.wallet_label)
            # Rotate bookkeeping: retire the old record when the server
            # says it replaced one.
            if current is not None and key.replaced:
                await self.state.retire_key(current.key_id, reason=reason)
            await self.state.save_key(KeyRecord(
                key_id=key.prefix,           # prefix is the durable identity
                secret=key.secret,           # shown exactly once — store now
                headroom_usd=0.0,            # gateway model: no per-key cap
                spend_usd=0.0,
                created_at=time.time(),
            ))
            kind = "key_rotated" if key.replaced else "key_created"
            title = "已轮换 key" if key.replaced else "已创建新 key"
            await self.state.log_event("info", kind, reason, {
                "prefix": key.prefix, "replaced": key.replaced,
                "base_url": key.base_url,
            })
            await self.notifier.notify(
                "success" if not key.replaced else "info",
                kind, title, reason,
                {"prefix": key.prefix, "replaced": key.replaced},
            )
            return

        if action == Action.REVOKE:
            await mcp.revoke_key()
            if current is not None:
                await self.state.retire_key(current.key_id, reason=reason)
            await self.state.log_event("error", "key_revoked", reason, {})
            await self.notifier.notify(
                "error", "key_revoked", "已撤销 key（疑似泄露）", reason, {}
            )
            return

        if action == Action.DELETE:
            result = await mcp.delete_key()
            await self.state.log_event("warn", "legacy_key_deleted", reason, {
                "refunded_usd": result.refunded_usd,
            })
            await self.notifier.notify(
                "warn", "legacy_key_deleted", "已清理旧版 key", reason,
                {"refunded_usd": result.refunded_usd},
            )
            return

    # ── Public properties for the dashboard ──────────────────────────

    @property
    def last_tick(self) -> TickReport | None:
        return self._last_tick

    @property
    def last_status(self) -> KeyStatus | None:
        return self._last_status


# ── Entrypoint helper ─────────────────────────────────────────────────────

async def _serve(bot: BagBot) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.request_stop)
    async with bot.require_mcp():
        await bot.run_forever()


def main() -> None:
    from .config import get_settings
    from .logging_setup import setup_logging  # local helper

    settings = get_settings()
    setup_logging(settings.log_file, settings.log_level)
    bot = BagBot(settings)
    asyncio.run(_serve(bot))
