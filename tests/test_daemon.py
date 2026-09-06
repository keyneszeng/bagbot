"""End-to-end daemon tick test using a fake MCP transport.

This is the highest-value test: it exercises config loading → state init →
daemon.tick() → decision → action → state update → notification.
"""

import asyncio
import json
from typing import Any

import httpx
import pytest

from bagbot.daemon import BagBot
from bagbot.orbio_mcp import KeyStatus


def _ok(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": payload})


def _structured(payload: dict[str, Any]) -> dict[str, Any]:
    return {"structuredContent": payload}


def _make_transport(handlers: dict[str, dict[str, Any]]):
    """Build a MockTransport that returns pre-canned responses per tool name."""
    def handler(req: httpx.Request) -> httpx.Response:
        # Extract the tool name from the JSON-RPC body
        try:
            body = json.loads(req.content.decode())
            tool = body.get("params", {}).get("name", "?")
        except Exception:
            tool = "?"
        if tool in handlers:
            return _ok(handlers[tool])
        return _ok(_structured({"earned": 0, "claimed": 0, "unclaimed": 0}))
    return httpx.MockTransport(handler)


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Make sure all secrets are empty so the daemon works in test mode
    monkeypatch.setenv("ORBIO_WALLET", "0xtest")
    monkeypatch.setenv("ORBIO_MCP_TOKEN", "tok")
    monkeypatch.setenv("ORBIO_MCP_URL", "https://x.example/mcp")
    monkeypatch.setenv("POLL_INTERVAL_SEC", "60")
    monkeypatch.setenv("WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("FEISHU_ENABLED", "false")
    monkeypatch.setenv("WECHAT_ENABLED", "false")
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("DASHBOARD_ENABLED", "false")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    return cfg_module.get_settings()


@pytest.mark.asyncio
async def test_first_tick_claims_when_no_key_and_balance_enough(tmp_settings):
    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 10.0, "claimed": 0.0, "unclaimed": 10.0}
        ),
        "orbio_claim_key": _structured(
            {"key_id": "k_first", "secret": "sk-first", "headroom": 200.0}
        ),
    }
    transport = _make_transport(handlers)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()

    report = await bot.tick()
    assert report.action.value == "claim"
    cur = await bot.state.current_key()
    assert cur is not None
    assert cur.key_id == "k_first"


@pytest.mark.asyncio
async def test_first_tick_alerts_when_no_key_and_balance_low(tmp_settings):
    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 1.0, "claimed": 0.0, "unclaimed": 1.0}
        ),
    }
    transport = _make_transport(handlers)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()

    report = await bot.tick()
    assert report.action.value == "alert"
    cur = await bot.state.current_key()
    assert cur is None  # no key was saved


@pytest.mark.asyncio
async def test_topup_when_key_used_past_threshold(tmp_settings):
    """Save a key with very high usage, then on the next tick the policy should top it up."""
    from bagbot.state import KeyRecord
    import time

    # spend=180, headroom=20 → used_fraction = 180/200 = 0.9 (> 0.8 threshold)
    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 50.0, "claimed": 0.0, "unclaimed": 50.0}
        ),
        "orbio_get_key_status": _structured({
            "key_id": "k_old", "spend": 180.0, "headroom": 20.0, "remaining": 20.0
        }),
        "orbio_top_up_key": _structured({
            "key_id": "k_old", "headroom": 220.0, "spend": 180.0
        }),
    }
    transport = _make_transport(handlers)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_old", secret="sk-old",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time() - 3600,
    ))

    report = await bot.tick()
    assert report.action.value == "topup"


@pytest.mark.asyncio
async def test_rotate_when_key_too_old(tmp_settings):
    from bagbot.state import KeyRecord
    import time

    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 0.5, "claimed": 0.5, "unclaimed": 0.0}
        ),
        "orbio_get_key_status": _structured({
            "key_id": "k_old", "spend": 10.0, "headroom": 200.0, "remaining": 190.0
        }),
        "orbio_rotate_key": _structured({
            "key_id": "k_new", "secret": "sk-new", "headroom": 0.0
        }),
    }
    transport = _make_transport(handlers)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_old", secret="sk-old",
        headroom_usd=200.0, spend_usd=10.0,
        # 8 days old, > 168h cap
        created_at=time.time() - 8 * 24 * 3600,
    ))

    report = await bot.tick()
    assert report.action.value == "rotate"

    # Old key should be retired
    keys = await bot.state.recent_keys(limit=10)
    old = next(k for k in keys if k.key_id == "k_old")
    assert old.retired_at is not None
    assert "age" in (old.retire_reason or "").lower()


@pytest.mark.asyncio
async def test_healthy_key_does_nothing(tmp_settings):
    from bagbot.state import KeyRecord
    import time

    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 5.0, "claimed": 5.0, "unclaimed": 0.0}
        ),
        "orbio_get_key_status": _structured({
            "key_id": "k_healthy", "spend": 5.0, "headroom": 200.0, "remaining": 195.0
        }),
    }
    transport = _make_transport(handlers)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_healthy", secret="sk-healthy",
        headroom_usd=200.0, spend_usd=5.0,
        created_at=time.time() - 3600,  # 1h old
    ))

    report = await bot.tick()
    assert report.action.value == "nothing"


@pytest.mark.asyncio
async def test_burn_rate_triggers_rotate(tmp_settings):
    """A high spend rate should trigger a rotation, even with a healthy balance."""
    from bagbot.state import KeyRecord
    import time

    # First call sets _last_status to baseline spend=0
    # Second call shows spend=50 over an instant — that gives a huge burn rate
    handlers = {
        "orbio_get_balance": _structured(
            {"earned": 50.0, "claimed": 0.0, "unclaimed": 50.0}
        ),
        "orbio_get_key_status_first": _structured({
            "key_id": "k_burn", "spend": 0.0, "headroom": 200.0, "remaining": 200.0
        }),
        "orbio_get_key_status": _structured({
            "key_id": "k_burn", "spend": 50.0, "headroom": 200.0, "remaining": 150.0
        }),
        "orbio_rotate_key": _structured({
            "key_id": "k_rotated", "secret": "sk-r", "headroom": 150.0
        }),
    }
    # Override transport to return different responses for the first vs subsequent
    # status calls.
    state = {"status_calls": 0}

    def handler(req):
        body = json.loads(req.content.decode())
        tool = body.get("params", {}).get("name", "?")
        if tool == "orbio_get_key_status":
            state["status_calls"] += 1
            if state["status_calls"] == 1:
                return _ok(handlers["orbio_get_key_status_first"])
            return _ok(handlers["orbio_get_key_status"])
        if tool in handlers:
            return _ok(handlers[tool])
        return _ok(_structured({"earned": 0, "claimed": 0, "unclaimed": 0}))

    transport = httpx.MockTransport(handler)

    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_burn", secret="sk-burn",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time() - 3600,
    ))

    # First tick: baseline, no decision yet because no burn rate history
    r1 = await bot.tick()
    assert r1.action.value in ("nothing", "topup")  # we set up a healthy key

    # Wait briefly so dt > 0 in burn rate calc
    await asyncio.sleep(0.05)

    # Second tick: spend jumped from 0 to 50, dt ~ 0.05s → huge rate
    r2 = await bot.tick()
    # At 50 USD / 0.05s = 3600 USD/h — way above 20 USD/h cap → rotate
    assert r2.action.value == "rotate"


@pytest.mark.asyncio
async def test_burn_rate_zero_dt_returns_zero(tmp_settings):
    """Defensive: if two consecutive status samples have the same ts (impossible
    in production, but the code path exists), burn rate should be 0, not Inf."""
    from bagbot.state import KeyRecord
    import time

    bot = BagBot(tmp_settings)
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_dt", secret="s",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time() - 3600,
    ))

    # Pin _last_status_ts to a fixed value AND freeze time.time so dt == 0
    fixed_ts = 1_700_000_000.0
    bot._last_status = KeyStatus(
        key_id="k_dt", spend_usd=10.0,
        headroom_usd=200.0, remaining_usd=190.0,
    )
    bot._last_status_ts = fixed_ts

    # Monkey-patch time.time so it returns exactly the same value
    real_time = time.time
    time.time = lambda: fixed_ts
    try:
        fresh = KeyStatus(
            key_id="k_dt", spend_usd=20.0,
            headroom_usd=200.0, remaining_usd=180.0,
        )
        rate = bot._compute_burn_rate(fresh)
    finally:
        time.time = real_time

    assert rate == 0.0, f"dt<=0 should return 0, got {rate}"


@pytest.mark.asyncio
async def test_burn_rate_zero_dt_strictly_less_than_returns_nonzero(tmp_settings):
    """Edge case: if dt is exactly 0, we return 0; if dt is a hair positive,
    we return a finite rate.  Regression test for the < vs <= boundary."""
    from bagbot.state import KeyRecord
    import time

    bot = BagBot(tmp_settings)
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_dt", secret="s",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time() - 3600,
    ))

    bot._last_status = KeyStatus(
        key_id="k_dt", spend_usd=0.0,
        headroom_usd=200.0, remaining_usd=200.0,
    )
    bot._last_status_ts = 100.0
    real_time = time.time
    time.time = lambda: 100.0 + 1e-9   # tiny positive dt
    try:
        fresh = KeyStatus(
            key_id="k_dt", spend_usd=1.0,
            headroom_usd=200.0, remaining_usd=199.0,
        )
        rate = bot._compute_burn_rate(fresh)
    finally:
        time.time = real_time

    # With dt=1e-9 and delta=1.0, rate = 1e9 USD/h — very large but finite
    assert rate > 0
    assert rate < float("inf")


@pytest.mark.asyncio
async def test_action_delete_calls_mcp_and_retires(tmp_settings):
    """Cover the DELETE branch which is currently only triggered by manual
    action (no policy action produces it).  Verify the I/O sequence."""
    from bagbot.state import KeyRecord
    import time

    delete_calls = {"n": 0}

    def handler(req):
        body = json.loads(req.content.decode())
        tool = body.get("params", {}).get("name", "?")
        if tool == "orbio_delete_key":
            delete_calls["n"] += 1
            return _ok(_structured({}))
        if tool == "orbio_get_balance":
            return _ok(_structured({"earned": 1, "claimed": 0, "unclaimed": 1}))
        if tool == "orbio_get_key_status":
            return _ok(_structured({
                "key_id": "k_del", "spend": 5, "headroom": 200, "remaining": 195
            }))
        return _ok(_structured({}))

    transport = httpx.MockTransport(handler)
    bot = BagBot(tmp_settings)
    bot.mcp._client = httpx.AsyncClient(transport=transport,
                                         base_url=bot.mcp.endpoint,
                                         headers={"Authorization": "Bearer tok"})
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_del", secret="s",
        headroom_usd=200.0, spend_usd=5.0,
        created_at=time.time() - 3600,
    ))

    # Manually drive the DELETE branch
    from bagbot.policy import Action
    await bot._execute(Action.DELETE, "test delete",
                        await bot.state.current_key(),
                        type("B", (), {
                            "earned_usd": 1, "claimed_usd": 0, "unclaimed_usd": 1
                        })(),
                        None)

    assert delete_calls["n"] == 1, "delete_key should have been called"
    cur = await bot.state.current_key()
    assert cur is None, "key should be retired after DELETE"


@pytest.mark.asyncio
async def test_action_alert_logs_event(tmp_settings):
    """Cover the ALERT branch — verify it logs an event."""
    from bagbot.policy import Action
    from unittest.mock import AsyncMock

    bot = BagBot(tmp_settings)
    await bot.state.init()
    # Replace notifier with a no-op so we don't accidentally try to deliver
    bot.notifier = AsyncMock()

    fake_balance = type("B", (), {
        "earned_usd": 1, "claimed_usd": 0, "unclaimed_usd": 0
    })()

    await bot._execute(Action.ALERT, "test alert", None, fake_balance, None)

    # An event row should be in the DB
    events = await bot.state.recent_events(limit=5)
    assert any(e["kind"] == "alert" for e in events)
