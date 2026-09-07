"""Mutation tests for the dashboard authentication code.

These tests are designed to be KILLED by the mutation tester.
Each one targets a specific decision point in the auth logic
and would fail (good!) if the code is mutated to bypass the check.

NOTE: All tests are designed to terminate before reaching the MCP.
We mock the MCP client so a single network retry cycle (3 × ~17s)
cannot blow up the test suite.

Run with:
    python scripts/mutation_test.py --module dashboard
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from bagbot.daemon import BagBot
from bagbot.dashboard import build_app
from bagbot.orbio_mcp import OrbioMCPError


def _setup_env(monkeypatch, *, dashboard_token: str | None = "secret") -> None:
    """Set the minimum env vars needed for Settings to construct."""
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


def _make_app(monkeypatch, *, dashboard_token: str | None = "secret"):
    """Build a FastAPI app with a mock MCP that returns instantly."""
    _setup_env(monkeypatch, dashboard_token=dashboard_token)
    from bagbot import config as cfg_module
    s = cfg_module.get_settings()
    bot = BagBot(s)
    # Replace the MCP client with an async mock that never hits the network.
    # Tests that pass auth will reach this mock and get a 502
    # (proving the auth check let them through).
    bot.mcp = MagicMock()
    bot.mcp.__aenter__ = AsyncMock(return_value=bot.mcp)
    bot.mcp.__aexit__ = AsyncMock(return_value=None)
    err = OrbioMCPError("claim_key", "mocked: should not reach MCP")
    bot.mcp.claim_key = AsyncMock(side_effect=err)
    bot.mcp.rotate_key = AsyncMock(side_effect=err)
    bot.mcp.top_up_key = AsyncMock(side_effect=err)
    return build_app(bot, s)


# ── _require_dashboard_token() boundary tests ────────────────────


def test_empty_token_disables_claim(monkeypatch):
    """No token in env → claim is blocked with 403."""
    app = _make_app(monkeypatch, dashboard_token=None)
    with TestClient(app) as client:
        r = client.post("/api/claim")
        assert r.status_code == 403
        assert "DASHBOARD_TOKEN" in r.json()["detail"]


def test_empty_token_disables_rotate(monkeypatch):
    app = _make_app(monkeypatch, dashboard_token=None)
    with TestClient(app) as client:
        r = client.post("/api/rotate")
        assert r.status_code == 403


def test_empty_token_disables_topup(monkeypatch):
    app = _make_app(monkeypatch, dashboard_token=None)
    with TestClient(app) as client:
        r = client.post("/api/topup", json={"amount": 10})
        assert r.status_code == 403


def test_whitespace_only_token_is_empty(monkeypatch):
    """A token of just whitespace is treated as empty (mutation: == vs .strip() == '')."""
    # Set token BEFORE _make_app runs _setup_env, so the .strip() in
    # _require_dashboard_token gets the whitespace string.
    monkeypatch.setenv("DASHBOARD_TOKEN", "   ")
    app = _make_app(monkeypatch, dashboard_token=None)  # don't overwrite
    # Manually re-set after _setup_env cleared it
    monkeypatch.setenv("DASHBOARD_TOKEN", "   ")
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    # Rebuild with the whitespace token
    s = cfg_module.get_settings()
    from bagbot.daemon import BagBot
    from bagbot.dashboard import build_app
    bot = BagBot(s)
    bot.mcp = MagicMock()
    app = build_app(bot, s)
    with TestClient(app) as client:
        r = client.post("/api/claim")
        # Should be 403 (disabled), not 401 (wrong token)
        assert r.status_code == 403


def test_correct_token_passes_auth(monkeypatch):
    """Correct X-Dashboard-Token header → passes auth (500 expected from mocked MCP)."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "secret"})
        # Auth passed → reached MCP mock → 500
        assert r.status_code in (500, 502), f"expected 500/502 (MCP mock), got {r.status_code}"


def test_correct_bearer_token_passes_auth(monkeypatch):
    """Authorization: Bearer <token> → also passes auth."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer secret"})
        assert r.status_code in (500, 502), f"expected 500/502, got {r.status_code}"


def test_wrong_token_returns_401(monkeypatch):
    """Wrong token → 401, NOT 403 (auth exists, just wrong key)."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "wrong"})
        assert r.status_code == 401


def test_wrong_token_via_bearer_returns_401(monkeypatch):
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


def test_non_bearer_authorization_header_ignored(monkeypatch):
    """A non-Bearer Authorization header is treated as missing token."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        # 'Basic' instead of 'Bearer' — should be treated as missing
        r = client.post("/api/claim", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401  # token missing/wrong


def test_get_endpoints_remain_unauthenticated(monkeypatch):
    """GET /, /api/state, /api/events, /api/balances work without token
    (the dashboard is read-only by default)."""
    app = _make_app(monkeypatch, dashboard_token=None)
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
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        # Provided token has leading whitespace — gets stripped, so matches
        # (proceeds past auth → reaches MCP mock → 500/502)
        r = client.post("/api/claim", headers={"X-Dashboard-Token": " secret"})
        assert r.status_code in (500, 502), f"expected 500/502, got {r.status_code}"


def test_truly_wrong_token_does_not_match(monkeypatch):
    """Even with .strip(), a different token is rejected."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"X-Dashboard-Token": "totally-different"})
        assert r.status_code == 401


def test_empty_bearer_token_rejected(monkeypatch):
    """Authorization: Bearer (empty) → 401, not 403."""
    app = _make_app(monkeypatch, dashboard_token="secret")
    with TestClient(app) as client:
        r = client.post("/api/claim", headers={"Authorization": "Bearer "})
        assert r.status_code == 401
