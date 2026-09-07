"""Example: pure-function decision on what to do with your balance.

No network. Just the policy engine:
    PYTHONPATH=skills/bagbot/scripts python3 examples/decide_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bagbot_policy  # noqa: E402


def show(label: str, snap: bagbot_policy.Snapshot, cfg) -> None:
    action, reason = bagbot_policy.decide(snap, cfg)
    print(f"{label:32s} → {action.value:8s}  ({reason})")


def main() -> None:
    cfg = bagbot_policy.PolicyConfig()
    print("Decisions with defaults (low_balance=5, topup=0.80, rotate=168h/20$h):")
    show("no key, $10 unclaimed", bagbot_policy.Snapshot(
        has_key=False, key_id=None, key_age_hours=0.0, spend_rate_usd_per_hour=0.0,
        key_used_fraction=0.0, key_remaining_usd=0.0, unclaimed_usd=10.0,
        earned_usd=10.0, claimed_usd=0.0), cfg)
    show("no key, $2 unclaimed", bagbot_policy.Snapshot(
        has_key=False, key_id=None, key_age_hours=0.0, spend_rate_usd_per_hour=0.0,
        key_used_fraction=0.0, key_remaining_usd=0.0, unclaimed_usd=2.0,
        earned_usd=2.0, claimed_usd=0.0), cfg)
    show("key 1h old, 10% used, $50 unclaimed", bagbot_policy.Snapshot(
        has_key=True, key_id="k1", key_age_hours=1.0, spend_rate_usd_per_hour=0.5,
        key_used_fraction=0.10, key_remaining_usd=180.0, unclaimed_usd=50.0,
        earned_usd=50.0, claimed_usd=20.0), cfg)
    show("key 10 days old", bagbot_policy.Snapshot(
        has_key=True, key_id="k2", key_age_hours=240.0, spend_rate_usd_per_hour=0.1,
        key_used_fraction=0.2, key_remaining_usd=160.0, unclaimed_usd=5.0,
        earned_usd=20.0, claimed_usd=15.0), cfg)
    show("key 85% used, $50 unclaimed", bagbot_policy.Snapshot(
        has_key=True, key_id="k3", key_age_hours=1.0, spend_rate_usd_per_hour=0.3,
        key_used_fraction=0.85, key_remaining_usd=30.0, unclaimed_usd=50.0,
        earned_usd=50.0, claimed_usd=20.0), cfg)
    show("burn rate $30/h", bagbot_policy.Snapshot(
        has_key=True, key_id="k4", key_age_hours=1.0, spend_rate_usd_per_hour=30.0,
        key_used_fraction=0.2, key_remaining_usd=160.0, unclaimed_usd=5.0,
        earned_usd=20.0, claimed_usd=15.0), cfg)


if __name__ == "__main__":
    main()
