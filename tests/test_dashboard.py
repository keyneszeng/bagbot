"""Dashboard route tests — using FastAPI TestClient (gateway model).

Endpoints under test:
  GET  /            — Chinese dashboard
  GET  /api/state   — JSON snapshot (no tick yet / ok shapes)
  POST /api/create  — mint (or rotate) the key — needs DASHBOARD_TOKEN
  POST /api/revoke  — stop the key — needs DASHBOARD_TOKEN
  POST /api/claim|/api/rotate — back-compat aliases of /api/create
  (POST /api/topup no longer exists — the gateway key spends the balance.)
"""

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


def test_create_without_token_returns_403(client):
    """Mutations are disabled when DASHBOARD_TOKEN is empty."""
    r = client.post("/api/create")
    assert r.status_code == 403
    assert "DASHBOARD_TOKEN" in r.json()["detail"]


def test_revoke_without_token_returns_403(client):
    """No token → revoke must be rejected before any state check."""
    r = client.post("/api/revoke")
    assert r.status_code == 403


def test_alias_claim_without_token_returns_403(client):
    """Back-compat alias /api/claim is gated the same way."""
    r = client.post("/api/claim")
    assert r.status_code == 403


def test_alias_rotate_without_token_returns_403(client):
    """Back-compat alias /api/rotate is gated the same way."""
    r = client.post("/api/rotate")
    assert r.status_code == 403


def test_topup_endpoint_retired(client):
    """The topup endpoint no longer exists in the gateway model."""
    r = client.post("/api/topup", json={"amount": 10})
    assert r.status_code in (404, 405)


@pytest.mark.asyncio
async def test_mutations_require_valid_token(settings, monkeypatch):
    """With a token configured, wrong/missing token → 401; valid proceeds."""
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret-test-token")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    await bot.state.init()
    app = build_app(bot, s)
    with TestClient(app) as client:
        # missing
        r = client.post("/api/create")
        assert r.status_code == 401
        # wrong
        r = client.post("/api/create", headers={"X-Dashboard-Token": "wrong"})
        assert r.status_code == 401
        # correct — proceeds past auth (hits real MCP → 502 in test env)
        r = client.post(
            "/api/create", headers={"X-Dashboard-Token": "secret-test-token"}
        )
        assert r.status_code in (200, 502)
        # Bearer style also accepted
        r = client.post(
            "/api/revoke",
            headers={"Authorization": "Bearer secret-test-token"},
        )
        assert r.status_code in (200, 502)


@pytest.mark.asyncio
async def test_create_returns_prefix_not_secret(settings, monkeypatch):
    """The create response must never contain the secret — only prefix."""
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret-test-token")
    from bagbot import config as cfg_module
    from unittest.mock import AsyncMock
    from bagbot.orbio_mcp import Key

    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    await bot.state.init()

    fake_key = Key(secret="sk-orbio-SUPERSECRET", prefix="sk-orbio-qq",
                  base_url="https://api.orbio.so/api/v1", replaced=False)

    class _MCP:
        create_key = AsyncMock(return_value=fake_key)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None

    bot.require_mcp = lambda: _MCP()  # type: ignore[method-assign]
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post(
            "/api/create", headers={"X-Dashboard-Token": "secret-test-token"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["prefix"] == "sk-orbio-qq"
        assert "sk-orbio-SUPERSECRET" not in r.text
        assert "secret" not in body


@pytest.mark.asyncio
async def test_revoke_retires_local_record(settings, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret-test-token")
    from bagbot import config as cfg_module
    from unittest.mock import AsyncMock
    from bagbot.orbio_mcp import RevokeResult

    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    await bot.state.init()
    await bot.state.save_key(KeyRecord(
        key_id="sk-orbio-old", secret="sk-old",
        headroom_usd=0.0, spend_usd=0.0,
        created_at=time.time(),
    ))

    class _MCP:
        revoke_key = AsyncMock(return_value=RevokeResult(revoked=True))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None

    bot.require_mcp = lambda: _MCP()  # type: ignore[method-assign]
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post(
            "/api/revoke", headers={"X-Dashboard-Token": "secret-test-token"}
        )
        assert r.status_code == 200
        assert r.json()["revoked"] is True
    cur = await bot.state.current_key()
    assert cur is None, "local key record should be retired after revoke"


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
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.get("/")
        # Template shows wallet[:10]…wallet[-6:]
        assert "0xabcdef01…cdef01" in r.text
