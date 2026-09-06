"""Tests for the policy decision engine."""

import pytest

from bagbot.policy import Action, PolicyConfig, Snapshot, decide


def make_snap(**overrides) -> Snapshot:
    base = dict(
        has_key=True,
        key_id="k_abc",
        key_age_hours=1.0,
        spend_rate_usd_per_hour=1.0,
        key_used_fraction=0.1,
        key_remaining_usd=180.0,
        unclaimed_usd=10.0,
        earned_usd=100.0,
        claimed_usd=50.0,
    )
    base.update(overrides)
    return Snapshot(**base)


def test_no_key_claims_when_balance_enough():
    cfg = PolicyConfig(low_balance_usd=5.0)
    snap = make_snap(has_key=False, unclaimed_usd=10.0)
    action, reason = decide(snap, cfg)
    assert action == Action.CLAIM
    assert "no key" in reason


def test_no_key_alerts_when_balance_low():
    cfg = PolicyConfig(low_balance_usd=5.0)
    snap = make_snap(has_key=False, unclaimed_usd=2.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ALERT
    assert "threshold" in reason


def test_key_too_old_triggers_rotate():
    cfg = PolicyConfig(rotate_max_age_hours=24)
    snap = make_snap(key_age_hours=25.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ROTATE
    assert "age" in reason


def test_burn_rate_too_high_triggers_rotate():
    cfg = PolicyConfig(rotate_burst_usd_per_hour=10.0)
    snap = make_snap(spend_rate_usd_per_hour=20.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ROTATE
    assert "burn rate" in reason


def test_high_usage_triggers_topup():
    cfg = PolicyConfig(topup_threshold=0.8, low_balance_usd=5.0)
    snap = make_snap(key_used_fraction=0.85, unclaimed_usd=50.0)
    action, reason = decide(snap, cfg)
    assert action == Action.TOPUP
    assert "topup" in reason.lower()


def test_high_usage_no_balance_rotates():
    cfg = PolicyConfig(topup_threshold=0.8, low_balance_usd=5.0)
    snap = make_snap(key_used_fraction=0.85, unclaimed_usd=0.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ROTATE


def test_healthy_state_does_nothing():
    cfg = PolicyConfig()
    snap = make_snap()
    action, reason = decide(snap, cfg)
    assert action == Action.NOTHING
    assert "healthy" in reason


def test_zero_remaining_rotates():
    cfg = PolicyConfig()
    snap = make_snap(key_remaining_usd=0.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ROTATE
    assert "remaining" in reason
