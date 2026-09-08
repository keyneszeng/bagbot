"""Tests for the policy decision engine (live Orbio gateway model).

Gateway semantics being pinned here:
  * creating a key is free → no key always means CREATE (balance is not a
    precondition; the key just spends whatever the balance holds);
  * rotation is CREATE (atomic replace) driven by age hygiene only;
  * leak = extreme burn rate → REVOKE (outranks age/legacy/alert);
  * legacy pre-gateway key present → DELETE (one-way refund cleanup);
  * low spendable balance is an ALERT — "hold more $ORBIO".
"""

import time

from bagbot.policy import CLAIM, ROTATE, Action, PolicyConfig, Snapshot, decide


def make_snap(**overrides) -> Snapshot:
    base = {
        "has_key": True,
        "key_prefix": "sk-orbio-ab12",
        "key_age_hours": 1.0,
        "spend_rate_usd_per_hour": 1.0,
        "balance_usd": 10.0,
        "accrued_usd": 100.0,
        "last_used_at": None,
        "has_legacy_key": False,
    }
    base.update(overrides)
    return Snapshot(**base)


def default_cfg() -> PolicyConfig:
    return PolicyConfig()


# ── No key → CREATE (costs nothing; balance is not a precondition) ────

def test_no_key_creates_even_with_low_balance():
    action, reason = decide(make_snap(has_key=False, balance_usd=0.1), default_cfg())
    assert action == Action.CREATE
    assert "no key" in reason


def test_no_key_creates_with_zero_balance():
    action, _ = decide(make_snap(has_key=False, balance_usd=0.0), default_cfg())
    assert action == Action.CREATE


def test_no_key_creates_when_balance_healthy():
    action, reason = decide(make_snap(has_key=False, balance_usd=50.0), default_cfg())
    assert action == Action.CREATE
    assert "creating" in reason


def test_leak_guard_requires_key():
    """High burn rate with NO key must not REVOKE — guard is `has_key and ...`."""
    cfg = PolicyConfig(leak_rate_usd_per_hour=50.0)
    action, _ = decide(make_snap(has_key=False, spend_rate_usd_per_hour=999.0), cfg)
    assert action == Action.CREATE


# ── Leak guard: burn rate ≥ threshold → REVOKE ───────────────────────

def test_burst_triggers_revoke():
    cfg = PolicyConfig(leak_rate_usd_per_hour=100.0)
    snap = make_snap(spend_rate_usd_per_hour=150.0)
    action, reason = decide(snap, cfg)
    assert action == Action.REVOKE
    assert "150.00/h" in reason


def test_burst_at_exact_threshold_revokes():
    """`>=` boundary: at equality must still revoke."""
    cfg = PolicyConfig(leak_rate_usd_per_hour=100.0)
    action, _ = decide(make_snap(spend_rate_usd_per_hour=100.0), cfg)
    assert action == Action.REVOKE


def test_burst_just_below_threshold_is_healthy():
    cfg = PolicyConfig(leak_rate_usd_per_hour=100.0)
    action, _ = decide(make_snap(spend_rate_usd_per_hour=99.99), cfg)
    assert action == Action.NOTHING


def test_burst_beats_age_rotation():
    """Leak guard must run before the age check."""
    cfg = PolicyConfig(rotate_max_age_hours=24, leak_rate_usd_per_hour=50.0)
    snap = make_snap(key_age_hours=100.0, spend_rate_usd_per_hour=60.0)
    action, _ = decide(snap, cfg)
    assert action == Action.REVOKE


# ── Age hygiene: old key → CREATE (atomic rotate) ────────────────────

def test_key_too_old_recreates():
    cfg = PolicyConfig(rotate_max_age_hours=24)
    snap = make_snap(key_age_hours=25.0)
    action, reason = decide(snap, cfg)
    assert action == Action.CREATE
    assert "age" in reason


def test_key_at_exact_age_limit_recreates():
    cfg = PolicyConfig(rotate_max_age_hours=24)
    action, _ = decide(make_snap(key_age_hours=24.0), cfg)
    assert action == Action.CREATE


def test_key_just_under_age_limit_is_healthy():
    cfg = PolicyConfig(rotate_max_age_hours=24)
    action, _ = decide(make_snap(key_age_hours=23.99), cfg)
    assert action == Action.NOTHING


def test_age_rotation_disabled_when_zero():
    """rotate_max_age_hours=0 means 'never rotate by age' (`> 0` gate)."""
    cfg = PolicyConfig(rotate_max_age_hours=0)
    snap = make_snap(key_age_hours=99999.0)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING


def test_age_rotation_beats_legacy_delete():
    """Order matters: recreate (age) outranks legacy cleanup."""
    cfg = PolicyConfig(rotate_max_age_hours=24)
    snap = make_snap(key_age_hours=100.0, has_legacy_key=True)
    action, _ = decide(snap, cfg)
    assert action == Action.CREATE


# ── Legacy cleanup ───────────────────────────────────────────────────

def test_legacy_key_triggers_delete():
    action, reason = decide(make_snap(has_legacy_key=True), default_cfg())
    assert action == Action.DELETE
    assert "legacy" in reason


def test_no_legacy_key_no_delete():
    action, _ = decide(make_snap(has_legacy_key=False), default_cfg())
    assert action == Action.NOTHING


def test_legacy_delete_beats_low_balance_alert():
    cfg = PolicyConfig(low_balance_usd=5.0)
    snap = make_snap(has_legacy_key=True, balance_usd=1.0)
    action, _ = decide(snap, cfg)
    assert action == Action.DELETE


# ── Balance alert: key healthy but bag running dry ───────────────────

def test_low_balance_alerts_with_key():
    cfg = PolicyConfig(low_balance_usd=5.0)
    snap = make_snap(balance_usd=2.0)
    action, reason = decide(snap, cfg)
    assert action == Action.ALERT
    assert "2.00" in reason


def test_balance_at_threshold_is_not_alert():
    """`< threshold` boundary: at equality the bag is fine."""
    cfg = PolicyConfig(low_balance_usd=5.0)
    action, _ = decide(make_snap(balance_usd=5.0), cfg)
    assert action == Action.NOTHING


def test_balance_just_above_threshold_is_healthy():
    cfg = PolicyConfig(low_balance_usd=5.0)
    action, _ = decide(make_snap(balance_usd=5.01), cfg)
    assert action == Action.NOTHING


# ── Baseline / misc ──────────────────────────────────────────────────

def test_healthy_state_is_nothing():
    action, reason = decide(make_snap(), default_cfg())
    assert action == Action.NOTHING
    assert reason == "healthy"


def test_snapshot_ts_defaults_to_now():
    snap = make_snap()
    assert abs(snap.ts - time.time()) < 2.0


def test_snapshot_ts_respects_explicit_value():
    assert make_snap(ts=123.0).ts == 123.0


def test_backcompat_aliases_point_to_create():
    assert CLAIM == Action.CREATE
    assert ROTATE == Action.CREATE
