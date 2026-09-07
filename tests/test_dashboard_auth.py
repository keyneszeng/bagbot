"""Mutation tests for the dashboard authentication code.

These tests are designed to be KILLED by the mutation tester.
Each one targets a specific decision point in the auth logic
and would fail (good!) if the code is mutated to bypass the check.

Run with:
    python scripts/mutation_test.py --module dashboard
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bagbot.daemon import BagBot
from bagbot.dashboard import build_app
from bagbot.state import KeyRecord


# Common test env.  The MCP token/wallet are required for Settings to
# construct (OrbioMCPClient raises on empty token).  The DASHBOARD_TOKEN
# is set per-test via monkeypatch.
def _setup_env(monkeypatch, *, dashboard_token: str | None = "secret") -> None:
    monkeypatch.setenv("ORBIO_WALLET", "0xtest")
    monkeypatch.setenv("ORBIO_MCP_TOKEN", "tok")
    monkeypatch.setenv("ORBIO_MCP_URL", "https://x.example/mcp")
    monkeypatch.setenv("DASHBOARD_ENABLED", "false")
    if dashboard_token is None:
        monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DASHBOARD_TOKEN", dashboard_token)
    from bagbot import config as cfg_module
    cfg_module.reload_settings()


def _make_client(monkeypatch, *, dashboard_token: str | None = "secret") -> TestClient:
    _setup_env(monkeypatch, dashboard_token=dashboard_token)
    s = _fresh_settings(monkeypatch)
    bot = _fresh_bot()
    app = build_app(bot, s)
    return TestClient(app)


def _fresh_settings(monkeypatch):
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    # Use a fresh DB path per test
    return s


def _fresh_bot():
    """Build a bot; the StateStore path will be set to a tmp path by the
    async fixture used in the test.  But the build_app needs s.dashboard etc.
    set up, so we just need the bot object."""
    import os
    s_path = f"/tmp/bagbot_test_auth_{os.getpid()}_{id(object())}.sqlite"
    if os.path.exists(s_path):
        os.unlink(s_path)
    from bagbot import config as cfg_module
    s = cfg_module.get_settings()
    s.state_db_path = s_path
    return BagBot(s)


# ── _require_dashboard_token() boundary tests ────────────────────


def test_empty_token_disables_claim(monkeypatch):
    """No token in env → claim is blocked with 403."""
    _setup_env(monkeypatch, dashboard_token=None)
    s = _fresh_settings(monkeypatch)
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim")
        assert r.status_code == 403
        assert "DASHBOARD_TOKEN" in r.json()["detail"]


def test_empty_token_disables_rotate(monkeypatch):
    _setup_env(monkeypatch, dashboard_token=None)
    s = _fresh_settings(monkeypatch)
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/rotate")
        assert r.status_code == 403


def test_empty_token_disables_topup(monkeypatch):
    _setup_env(monkeypatch, dashboard_token=None)
    s = _fresh_settings(monkeypatch)
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/topup", json={"amount": 10})
        assert r.status_code == 403


def test_whitespace_only_token_is_empty(monkeypatch):
    """A token of just whitespace is treated as empty (mutation: == vs .strip() == '')."""
    monkeypatch.setenv("DASHBOARD_TOKEN", "   ")
    _setup_env(monkeypatch, dashboard_token=None)  # we set manually above
    monkeypatch.setenv("DASHBOARD_TOKEN", "   ")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim")
        # Should be 403 (disabled), not 401 (wrong token)
        assert r.status_code == 403


def test_correct_token_passes_auth(monkeypatch):
    """Correct X-Dashboard-Token header → passes auth (may 502 on MCP)."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "secret"})
        # 200 (key returned but no secret), 500 (no MCP), 502 (MCP error) all OK
        assert r.status_code in (200, 500, 502)
        if r.status_code == 200:
            # Critical: response must NOT contain the secret
            body = r.json()
            assert "secret" not in body
            assert "sk-or" not in str(body)


def test_correct_bearer_token_passes_auth(monkeypatch):
    """Authorization: Bearer <token> → also passes auth."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer secret"})
        assert r.status_code in (200, 500, 502)


def test_wrong_token_returns_401(monkeypatch):
    """Wrong token → 401, NOT 403 (auth exists, just wrong key)."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "wrong"})
        assert r.status_code == 401


def test_wrong_token_via_bearer_returns_401(monkeypatch):
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


def test_non_bearer_authorization_header_ignored(monkeypatch):
    """A non-Bearer Authorization header is treated as missing token."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        # 'Basic' instead of 'Bearer' — should be treated as missing
        r = client.post("/api/claim", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401  # token missing/wrong


def test_get_endpoints_remain_unauthenticated(monkeypatch):
    """GET /, /api/state, /api/events, /api/balances work without token
    (the dashboard is read-only by default)."""
    _setup_env(monkeypatch, dashboard_token=None)
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        # All GETs should work without any auth header
        assert client.get("/").status_code == 200
        assert client.get("/api/state").status_code == 200
        assert client.get("/api/events").status_code == 200
        assert client.get("/api/balances").status_code == 200


def test_token_comparison_trims_whitespace_on_both_sides(monkeypatch):
    """The expected token is stripped (.strip()) and so is the provided one
    — leading/trailing whitespace on either side is ignored.  This is
    intentional (avoids header parsing confusion) — but a future refactor
    that drops .strip() would fail this test in an unexpected direction."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        # Provided token has leading whitespace — gets stripped, so matches
        # (proceeds past auth → may 502 on MCP, but NOT 401)
        r = client.post("/api/claim", headers={"X-Dashboard-Token": " secret"})
        assert r.status_code in (200, 500, 502)


def test_truly_wrong_token_does_not_match(monkeypatch):
    """Even with .strip(), a different token is rejected."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "totally-different"})
        assert r.status_code == 401


def test_empty_bearer_token_rejected(monkeypatch):
    """Authorization: Bearer (empty) → 401, not 403."""
    _setup_env(monkeypatch, dashboard_token="secret")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    bot = BagBot(s)
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer "})
        assert r.status_code == 401
