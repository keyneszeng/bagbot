"""Core BagBot daemon — the 7×24 event loop.

Lifecycle per tick (every POLL_INTERVAL_SEC seconds):
  1.  Read balance (orbio_get_balance)
  2.  Read current key status (orbio_get_key_status), if any
  3.  Compute spend rate from the last 2-3 balance snapshots
  4.  Decide an action (policy.decide)
  5.  Execute the action
  6.  Persist state + emit notification
  7.  Sleep
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from typing import Optional

from .config import Settings
from .notifier import Notifier
from .orbio_mcp import (
    Balance,
    Key,
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
    status: Optional[KeyStatus]
    action: Action
    reason: str


class BagBot:
    def __init__(self, settings: Settings):
        self.cfg = settings
        self.policy = PolicyConfig(
            low_balance_usd=settings.low_balance_usd,
            topup_threshold=settings.topup_threshold,
            rotate_max_age_hours=settings.rotate_max_age_hours,
            rotate_burst_usd_per_hour=settings.rotate_burst_usd_per_hour,
            key_cap_usd=settings.key_cap_usd,
        )
        self.state = StateStore(settings.state_db_path)
        self.notifier = Notifier(settings.notifier, lang=settings.language)
        self.mcp = OrbioMCPClient(
            endpoint=settings.orbio_mcp_url, token=settings.orbio_mcp_token
        )
        self._stop_event = asyncio.Event()
        self._last_tick: Optional[TickReport] = None
        self._last_status: Optional[KeyStatus] = None
        self._last_status_ts: float = 0.0

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
        balance = await self.mcp.get_balance()
        await self.state.record_balance(
            balance.earned_usd, balance.claimed_usd, balance.unclaimed_usd
        )

        current = await self.state.current_key()
        status: Optional[KeyStatus] = None
        if current is not None:
            try:
                status = await self.mcp.get_key_status(current.key_id)
            except OrbioMCPError as e:
                log.warning("could not read key status: %s", e)
                status = None

        # Burn rate from history.
        burn_rate = self._compute_burn_rate(status)

        # Use sentinel 0.0 for everything key-related if we couldn't read status.
        snap = Snapshot(
            has_key=current is not None,
            key_id=current.key_id if current else None,
            key_age_hours=(
                (time.time() - current.created_at) / 3600.0 if current else 0.0
            ),
            spend_rate_usd_per_hour=burn_rate,
            key_used_fraction=status.used_fraction if status is not None else 0.0,
            key_remaining_usd=status.remaining_usd if status is not None else 0.0,
            unclaimed_usd=balance.unclaimed_usd,
            earned_usd=balance.earned_usd,
            claimed_usd=balance.claimed_usd,
        )

        action, reason = decide(snap, self.policy)
        log.info("tick: bal=$%.2f unclaimed key=%s action=%s reason=%s",
                 balance.unclaimed_usd, snap.key_id or "-", action.value, reason)

        await self._execute(action, reason, current, balance, status)
        report = TickReport(
            ts=time.time(), balance=balance, status=status,
            action=action, reason=reason,
        )
        self._last_tick = report
        if status is not None:
            self._last_status = status
            self._last_status_ts = time.time()
        return report

    # ── Helpers ──────────────────────────────────────────────────────

    def _compute_burn_rate(self, status: Optional[KeyStatus]) -> float:
        """Estimate USD/hour of key spend.

        For now: if we have a previous status sample, divide its spend delta
        by the elapsed wall time.  Returns 0.0 if not enough data.
        """
        if status is None or self._last_status is None:
            return 0.0
        dt = time.time() - self._last_status_ts
        if dt <= 0:
            return 0.0
        delta = max(0.0, status.spend_usd - self._last_status.spend_usd)
        return (delta / dt) * 3600.0

    async def _execute(
        self,
        action: Action,
        reason: str,
        current: Optional[KeyRecord],
        balance: Balance,
        status: Optional[KeyStatus],
    ) -> None:
        if action == Action.NOTHING:
            return

        # ALERT is special: it can fire even when there's no current key
        # (the policy emits ALERT when there is no key and balance is low).
        # It must run BEFORE the "current is None" guard below.
        if action == Action.ALERT:
            await self.state.log_event("warn", "alert", reason, {
                "unclaimed_usd": balance.unclaimed_usd,
            })
            await self.notifier.notify(
                "warn", "balance_low", "未领取余额偏低", reason,
                {"unclaimed": balance.unclaimed_usd,
                 "threshold": self.policy.low_balance_usd},
            )
            return

        if action == Action.CLAIM:
            key = await self.mcp.claim_key(cap_usd=self.policy.key_cap_usd)
            await self.state.save_key(KeyRecord(
                key_id=key.key_id, secret=key.secret,
                headroom_usd=key.headroom_usd, spend_usd=0.0,
                created_at=time.time(),
            ))
            await self.state.log_event("info", "key_claimed", reason, {
                "key_id": key.key_id, "headroom_usd": key.headroom_usd,
            })
            await self.notifier.notify(
                "success", "key_claimed", "已领取新 key",
                reason,
                {"headroom": key.headroom_usd},
            )
            return

        # All other actions (TOPUP, ROTATE, DELETE) need a current key.
        if current is None:
            log.warning("action %s requested but no current key", action.value)
            return

        if action == Action.TOPUP:
            amount = min(self.policy.key_cap_usd, max(1.0, balance.unclaimed_usd))
            new_key = await self.mcp.top_up_key(current.key_id, amount)
            await self.state.save_key(KeyRecord(
                key_id=new_key.key_id, secret=current.secret,
                headroom_usd=new_key.headroom_usd,
                spend_usd=new_key.spend_usd,
                created_at=current.created_at,
            ))
            await self.state.log_event("info", "key_topped_up", reason, {
                "amount_usd": amount, "key_id": current.key_id,
            })
            await self.notifier.notify(
                "info", "key_topped_up", "已为 key 充值", reason,
                {"amount": amount},
            )
            return

        if action == Action.ROTATE:
            new_key = await self.mcp.rotate_key(current.key_id)
            await self.state.retire_key(current.key_id, reason=reason)
            await self.state.save_key(KeyRecord(
                key_id=new_key.key_id, secret=new_key.secret,
                headroom_usd=new_key.headroom_usd, spend_usd=0.0,
                created_at=time.time(),
            ))
            await self.state.log_event("warn", "key_rotated", reason, {
                "old_key_id": current.key_id, "new_key_id": new_key.key_id,
            })
            await self.notifier.notify(
                "warn", "key_rotated", "已轮换 key", reason,
                {"reason": reason},
            )
            return

        if action == Action.DELETE:
            await self.mcp.delete_key(current.key_id)
            await self.state.retire_key(current.key_id, reason=reason)
            await self.state.log_event("error", "key_deleted", reason, {
                "key_id": current.key_id,
            })
            await self.notifier.notify(
                "error", "key_deleted", "已停用 key", reason,
                {"reason": reason},
            )
            return

    # ── Public properties for the dashboard ──────────────────────────

    @property
    def last_tick(self) -> Optional[TickReport]:
        return self._last_tick

    @property
    def last_status(self) -> Optional[KeyStatus]:
        return self._last_status


# ── Entrypoint helper ─────────────────────────────────────────────────────

async def _serve(bot: BagBot) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.request_stop)
    async with bot.mcp:
        await bot.run_forever()


def main() -> None:
    from .config import get_settings
    from .logging_setup import setup_logging  # local helper

    settings = get_settings()
    setup_logging(settings.log_file, settings.log_level)
    bot = BagBot(settings)
    asyncio.run(_serve(bot))
