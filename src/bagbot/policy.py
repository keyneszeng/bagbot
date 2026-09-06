"""Pluggable decision policy for the daemon.

Pure functions over a snapshot of state → (action, reason).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Action(str, Enum):
    NOTHING = "nothing"
    CLAIM = "claim"
    TOPUP = "topup"
    ROTATE = "rotate"
    DELETE = "delete"
    ALERT = "alert"


@dataclass
class Snapshot:
    has_key: bool
    key_id: Optional[str]
    key_age_hours: float
    spend_rate_usd_per_hour: float
    key_used_fraction: float        # 0..1
    key_remaining_usd: float
    unclaimed_usd: float
    earned_usd: float
    claimed_usd: float
    ts: float = 0.0

    def __post_init__(self):
        if self.ts == 0.0:
            self.ts = time.time()


@dataclass
class PolicyConfig:
    low_balance_usd: float = 5.0
    topup_threshold: float = 0.8
    rotate_max_age_hours: int = 168   # 7 days
    rotate_burst_usd_per_hour: float = 20.0
    key_cap_usd: float = 200.0


def decide(snap: Snapshot, cfg: PolicyConfig) -> tuple[Action, str]:
    """Pure decision function. Easy to unit-test."""

    # No key yet.
    if not snap.has_key:
        if snap.unclaimed_usd >= cfg.low_balance_usd:
            return Action.CLAIM, "no key yet; balance is enough to claim"
        return Action.ALERT, (
            f"no key and unclaimed ${snap.unclaimed_usd:.2f} < "
            f"threshold ${cfg.low_balance_usd:.2f}"
        )

    # Key too old.
    if cfg.rotate_max_age_hours > 0 and snap.key_age_hours >= cfg.rotate_max_age_hours:
        return Action.ROTATE, (
            f"key age {snap.key_age_hours:.1f}h ≥ {cfg.rotate_max_age_hours}h cap"
        )

    # Burn rate suspicious.
    if snap.spend_rate_usd_per_hour >= cfg.rotate_burst_usd_per_hour:
        return Action.ROTATE, (
            f"key burn rate ${snap.spend_rate_usd_per_hour:.2f}/h ≥ "
            f"${cfg.rotate_burst_usd_per_hour:.2f}/h cap"
        )

    # Headroom running low → top up.
    if snap.key_used_fraction >= cfg.topup_threshold:
        if snap.unclaimed_usd >= 1.0:
            return Action.TOPUP, (
                f"key used {snap.key_used_fraction:.0%} ≥ "
                f"topup threshold {cfg.topup_threshold:.0%}"
            )
        return Action.ROTATE, (
            "key used past topup threshold but no balance to top up; rotating"
        )

    # Headroom fully drained (race).
    if snap.key_remaining_usd <= 0:
        return Action.ROTATE, "key remaining ≤ 0"

    return Action.NOTHING, "healthy"
