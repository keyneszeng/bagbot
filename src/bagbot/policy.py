"""Pluggable decision policy for the daemon.

Pure functions over a snapshot of state → (action, reason).

Actions map onto the **live Orbio gateway API** (verified 2026-09-08):

  CREATE  → orbio_create_key   (mint key; also the rotation / leak-response)
  REVOKE  → orbio_revoke_key   (stop key; balance untouched)
  DELETE  → orbio_delete_key   (legacy pre-gateway key cleanup only)
  ALERT   → notify only

Gateway model — why the rules are simple:
  * the key holds **no credit**: it spends the account balance directly, so
    there is no top-up and no per-key cap/usage fraction;
  * creating a key costs nothing: no key → create immediately;
  * rotation is create-again (old key retired atomically, replaced=true);
  * the two real risks: a leaked key burning the bag (burn-rate guard),
    and a long-lived secret (age hygiene) — plus "balance low", which just
    alerts the human to hold more $ORBIO.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    NOTHING = "nothing"
    CREATE = "create"      # orbio_create_key (mint / rotate / leak-replace)
    REVOKE = "revoke"      # orbio_revoke_key
    DELETE = "delete"      # orbio_delete_key (legacy cleanup)
    ALERT = "alert"


# Backwards-compat aliases for older callers/tests.
CLAIM = Action.CREATE
ROTATE = Action.CREATE


@dataclass
class Snapshot:
    has_key: bool
    key_prefix: str | None          # visible head, e.g. sk-orbio-ab12
    key_age_hours: float
    spend_rate_usd_per_hour: float  # measured from balance history
    balance_usd: float              # spendable now (the quota)
    accrued_usd: float              # lifetime earned
    last_used_at: float | None      # epoch; None = never used
    has_legacy_key: bool = False    # pre-gateway OpenRouter key pending cleanup
    ts: float = 0.0

    def __post_init__(self):
        if self.ts == 0.0:
            self.ts = time.time()


@dataclass
class PolicyConfig:
    low_balance_usd: float = 5.0           # balance below this → alert
    rotate_max_age_hours: int = 168        # 7 days; 0 disables
    leak_rate_usd_per_hour: float = 100.0  # burn above this → revoke (leak)


def decide(snap: Snapshot, cfg: PolicyConfig) -> tuple[Action, str]:
    """Pure decision function. Easy to unit-test."""

    # ── Leak guard first: a burning key outranks everything ──────────
    if snap.has_key and snap.spend_rate_usd_per_hour >= cfg.leak_rate_usd_per_hour:
        return Action.REVOKE, (
            f"burn rate ${snap.spend_rate_usd_per_hour:.2f}/h ≥ "
            f"leak threshold ${cfg.leak_rate_usd_per_hour:.2f}/h; revoking"
        )

    # ── No key → create one (costs nothing in gateway model) ─────────
    if not snap.has_key:
        return Action.CREATE, "no key yet; creating (key is free, spends balance)"

    # ── Hygiene: rotate on age via atomic re-create ──────────────────
    if cfg.rotate_max_age_hours > 0 and snap.key_age_hours >= cfg.rotate_max_age_hours:
        return Action.CREATE, (
            f"key age {snap.key_age_hours:.1f}h ≥ {cfg.rotate_max_age_hours}h cap; "
            "recreating (old key retired atomically)"
        )

    # ── Legacy pre-gateway key pending cleanup ───────────────────────
    if snap.has_legacy_key:
        return Action.DELETE, "legacy pre-gateway key present; deleting refunds it"

    # ── Balance low: alert (the key is fine; the bag is running dry) ─
    if snap.balance_usd < cfg.low_balance_usd:
        return Action.ALERT, (
            f"balance ${snap.balance_usd:.2f} < alert threshold "
            f"${cfg.low_balance_usd:.2f}"
        )

    # Healthy: the gateway auto-draws the balance; nothing to do.
    return Action.NOTHING, "healthy"
