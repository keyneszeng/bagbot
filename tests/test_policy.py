"""Tests for the policy decision engine."""


from bagbot.policy import Action, PolicyConfig, Snapshot, decide


def make_snap(**overrides) -> Snapshot:
    base = {
        "has_key": True,
        "key_id": "k_abc",
        "key_age_hours": 1.0,
        "spend_rate_usd_per_hour": 1.0,
        "key_used_fraction": 0.1,
        "key_remaining_usd": 180.0,
        "unclaimed_usd": 10.0,
        "earned_usd": 100.0,
        "claimed_usd": 50.0,
    }
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


def test_small_positive_remaining_does_not_rotate():
    """A small but positive remaining should be healthy, not a rotate."""
    cfg = PolicyConfig()
    snap = make_snap(key_remaining_usd=0.5)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING


def test_negative_remaining_rotates():
    """Defensive: negative remaining (shouldn't happen, but if it does) rotates."""
    cfg = PolicyConfig()
    snap = make_snap(key_remaining_usd=-1.0)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE


# ── Boundary tests (kill mutation survivors) ─────────────────────────


def test_unclaimed_exactly_at_low_balance_triggers_claim():
    """`unclaimed >= low_balance` — the >= boundary must be inclusive."""
    cfg = PolicyConfig(low_balance_usd=5.0)
    snap = make_snap(has_key=False, unclaimed_usd=5.0)
    action, _ = decide(snap, cfg)
    assert action == Action.CLAIM, "unclaimed == low_balance should claim"


def test_key_age_exactly_at_max_triggers_rotate():
    """`key_age >= max_age` — at equality, rotate. Just past, rotate. Below, not."""
    cfg = PolicyConfig(rotate_max_age_hours=24)
    snap = make_snap(key_age_hours=24.0)
    action, _ = decide(snap, cfg)
    # Exactly at cap: rotate (uses >=)
    assert action == Action.ROTATE
    # Just under cap: NOT a rotate
    snap = make_snap(key_age_hours=23.99)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING
    # Just over cap: rotate
    snap = make_snap(key_age_hours=24.01)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE


def test_burn_rate_exactly_at_threshold_triggers_rotate():
    """`spend_rate >= threshold` — at equality, still rotates."""
    cfg = PolicyConfig(rotate_burst_usd_per_hour=20.0)
    snap = make_snap(spend_rate_usd_per_hour=20.0)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE, "burn rate at exact threshold should rotate"

    snap = make_snap(spend_rate_usd_per_hour=19.99)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING


def test_topup_at_exact_threshold_triggers_topup():
    """`used_fraction >= topup_threshold` — at equality, topup."""
    cfg = PolicyConfig(topup_threshold=0.8, low_balance_usd=5.0)
    snap = make_snap(key_used_fraction=0.8, unclaimed_usd=10.0)
    action, _ = decide(snap, cfg)
    assert action == Action.TOPUP, "used == threshold should topup"

    snap = make_snap(key_used_fraction=0.7999, unclaimed_usd=10.0)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING


def test_topup_at_exact_threshold_no_balance_rotates():
    """Boundary: at threshold with unclaimed==0, must rotate (not nothing)."""
    cfg = PolicyConfig(topup_threshold=0.8, low_balance_usd=5.0)
    snap = make_snap(key_used_fraction=0.8, unclaimed_usd=0.0)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE


def test_unclaimed_just_above_zero_allows_topup():
    """The `unclaimed >= 1.0` gate for topup — at exactly 0, must not topup;
    at 1.0+, must topup; in between, must rotate."""
    cfg = PolicyConfig(topup_threshold=0.5, low_balance_usd=5.0)
    # At threshold, unclaimed == 0 → rotate (not topup, since < $1.00)
    snap = make_snap(key_used_fraction=0.6, unclaimed_usd=0.0)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE
    # At threshold, unclaimed 0.5 (below $1) → still rotate
    snap = make_snap(key_used_fraction=0.6, unclaimed_usd=0.5)
    action, _ = decide(snap, cfg)
    assert action == Action.ROTATE
    # At threshold, unclaimed exactly 1.0 → topup (>= boundary)
    snap = make_snap(key_used_fraction=0.6, unclaimed_usd=1.0)
    action, _ = decide(snap, cfg)
    assert action == Action.TOPUP


def test_rotate_max_age_zero_disables_rotation_by_age():
    """rotate_max_age_hours=0 should mean 'never rotate by age'.
    The policy uses `> 0` to gate the check, so 0 disables it."""
    cfg = PolicyConfig(rotate_max_age_hours=0)
    snap = make_snap(key_age_hours=99999.0)
    action, _ = decide(snap, cfg)
    assert action == Action.NOTHING, (
        "rotate_max_age_hours=0 should disable rotation-by-age"
    )
