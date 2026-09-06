"""Dashboard route tests — using FastAPI TestClient + async fixtures."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from bagbot.daemon import BagBot
from bagbot.dashboard import build_app
from bagbot.state import KeyRecord


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORBIO_WALLET", "0xtest")
    monkeypatch.setenv("ORBIO_MCP_TOKEN", "tok")
    monkeypatch.setenv("ORBIO_MCP_URL", "https://x.example/mcp")
    monkeypatch.setenv("DASHBOARD_ENABLED", "false")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    return cfg_module.get_settings()


@pytest.fixture
async def bot_with_state(settings):
    bot = BagBot(settings)
    await bot.state.init()
    return bot


@pytest.fixture
def client(bot_with_state, settings):
    """Sync wrapper that runs the bot init then builds the app."""
    app = build_app(bot_with_state, settings)
    return TestClient(app)


def test_dashboard_renders_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "BagBot" in r.text
    assert "0xtest" in r.text  # wallet address (truncated in template)


def test_api_state_when_no_tick_yet(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "no_tick_yet"


def test_claim_without_mcp_returns_error(client):
    """bot.mcp is not initialised via async ctx manager here, so claim
    should fail with 500 (AttributeError) or 502 (OrbioMCPError)."""
    r = client.post("/api/claim")
    assert r.status_code in (500, 502)


def test_rotate_without_current_key_returns_400(client):
    """No saved key in state → rotate should refuse with 400."""
    r = client.post("/api/rotate")
    assert r.status_code == 400
    assert "no current key" in r.json()["detail"]


def test_topup_without_current_key_returns_400(client):
    """No saved key → topup should refuse with 400."""
    r = client.post("/api/topup", json={"amount": 10})
    assert r.status_code == 400
    assert "no current key" in r.json()["detail"]


@pytest.mark.asyncio
async def test_topup_validates_positive_amount(settings):
    """Even with a current key, amount must be in (0, cap]."""
    bot = BagBot(settings)
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="k_test", secret="sk-test",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time(),
    ))
    app = build_app(bot, settings)
    with TestClient(app) as client:
        r = client.post("/api/topup", json={"amount": -5})
        assert r.status_code == 400
        r = client.post("/api/topup", json={"amount": 500})  # > cap
        assert r.status_code == 400
        r = client.post("/api/topup", json={"amount": 0})
        assert r.status_code == 400


def test_events_endpoint_returns_array(client):
    r = client.get("/api/events?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_balances_endpoint_returns_array(client):
    r = client.get("/api/balances?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_wallet_truncation_in_template(settings, tmp_path, monkeypatch):
    """Long wallet address should be truncated in the header."""
    monkeypatch.setenv("ORBIO_WALLET", "0xabcdef0123456789abcdef0123456789abcdef01")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    # No state init needed for index render
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.get("/")
        # Template shows wallet[:10]…wallet[-6:]
        # "0xabcdef0123456789abcdef0123456789abcdef01" → first 10 = "0xabcdef01", last 6 = "cdef01"
        assert "0xabcdef01…cdef01" in r.text
