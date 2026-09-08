"""End-to-end daemon tick tests using a fake MCP transport (gateway model).

This is the highest-value test: it exercises config loading → state init →
daemon.tick() → decision → action → state update → notification, against
the live Orbio gateway payload shapes ({"usd", "microUsd"}, hasKey/prefix…).
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from bagbot.daemon import BagBot
from bagbot.state import KeyRecord


def _ok(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": payload})


def _structured(payload: dict[str, Any]) -> dict[str, Any]:
    return {"structuredContent": payload}


def _balance(spendable: float, accrued: float = 100.0) -> dict[str, Any]:
    return _structured({
        "wallets": ["0xtest"],
        "accrued": {"usd": accrued, "microUsd": str(int(accrued * 1_000_000))},
        "purchased": {"usd": 0, "microUsd": "0"},
        "spent": {"usd": 0, "microUsd": "0"},
        "claimed": {"usd": 0, "microUsd": "0"},
        "balance": {"usd": spendable, "microUsd": str(int(spendable * 1_000_000))},
    })


def _status(has: bool, prefix: str | None = "sk-orbio-ab12",
            created_hours_ago: float = 1.0) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    created = (datetime.now(timezone.utc)
               - timedelta(hours=created_hours_ago)).isoformat()
    return _structured({
        "hasKey": has,
        "prefix": prefix if has else None,
        "createdAt": created if has else None,
        "lastUsedAt": None,
        "baseUrl": "https://api.orbio.so/api/v1",
        "legacy": None,
    })


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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


@asynccontextmanager
async def mocked(handlers: dict[str, Any]):
    """Transport that serves canned responses per tool name."""
    def handler(req: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(req.content.decode())
            tool = body.get("params", {}).get("name", "?")
        except Exception:
            tool = "?"
        if tool in handlers:
            return _ok(handlers[tool])
        return _ok(_balance(0.0))
    transport = httpx.MockTransport(handler)

    class _MCPProxy:
        """Minimal duck-type of OrbioMCPClient for the daemon tick."""
        endpoint = "https://x.example/mcp"
        token = "tok"

        def __init__(self):
            self._client = httpx.AsyncClient(
                transport=transport, base_url=self.endpoint,
                headers={"Authorization": "Bearer tok"},
            )
            self.calls: list[str] = []

        async def _call(self, tool, arguments=None):
            from bagbot.orbio_mcp import OrbioMCPError
            self.calls.append(tool)
            try:
                body = json.loads(
                    (await self._client.post(self.endpoint, json={
                        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": tool, "arguments": arguments or {}},
                    })).content.decode()
                )
            except Exception as e:  # pragma: no cover
                raise OrbioMCPError(tool, str(e))
            if "error" in body:
                raise OrbioMCPError(tool, str(body["error"]))
            return body.get("result", {}).get("structuredContent", {})

        async def get_balance(self):
            from bagbot.orbio_mcp import Balance
            return Balance.from_payload(await self._call("orbio_get_balance"))

        async def get_key_status(self):
            from bagbot.orbio_mcp import KeyStatus
            return KeyStatus.from_payload(await self._call("orbio_get_key_status"))

        async def create_key(self, label=None):
            from bagbot.orbio_mcp import Key
            return Key(secret="sk-orb-NEW", prefix="sk-orbio-new1", base_url="https://api.orbio.so/api/v1", replaced=True,
            ) if "orbio_create_key" in handlers else Key(
                secret="sk-orb-NEW", prefix="sk-orbio-new1",
                base_url="https://api.orbio.so/api/v1", replaced=False)

        async def revoke_key(self):
            from bagbot.orbio_mcp import RevokeResult
            return RevokeResult(revoked=True)

        async def delete_key(self):
            from bagbot.orbio_mcp import DeleteResult
            return DeleteResult(refunded_usd=0.0)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    proxy = _MCPProxy()
    try:
        yield proxy
    finally:
        await proxy._client.aclose()


# ── tick → decision → action ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_tick_creates_when_no_key(tmp_settings):
    async with mocked({
        "orbio_get_balance": _balance(10.0),
        "orbio_get_key_status": _status(False),
        "orbio_create_key": _structured({
            "key": "sk-orb-NEW", "prefix": "sk-orbio-new1",
            "baseUrl": "https://api.orbio.so/api/v1", "replaced": False}),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()

        report = await bot.tick()
        assert report.action.value == "create"
        cur = await bot.state.current_key()
        assert cur is not None
        assert cur.key_id == "sk-orbio-new1"
        assert cur.secret == "sk-orb-NEW"  # secret stored exactly once


@pytest.mark.asyncio
async def test_first_tick_creates_even_with_zero_balance(tmp_settings):
    """Gateway: key is free; a zero balance must not block creation."""
    async with mocked({
        "orbio_get_balance": _balance(0.0),
        "orbio_get_key_status": _status(False),
        "orbio_create_key": _structured({
            "key": "k", "prefix": "sk-orbio-zz",
            "baseUrl": "b", "replaced": False}),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        report = await bot.tick()
        assert report.action.value == "create"


@pytest.mark.asyncio
async def test_healthy_key_does_nothing(tmp_settings):
    async with mocked({
        "orbio_get_balance": _balance(50.0),
        "orbio_get_key_status": _status(True, created_hours_ago=1.0),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        await bot.state.save_key(KeyRecord(
            key_id="sk-orbio-ab12", secret="sk-old",
            headroom_usd=0.0, spend_usd=0.0,
            created_at=time.time() - 3600,
        ))
        report = await bot.tick()
        assert report.action.value == "nothing"


@pytest.mark.asyncio
async def test_old_key_recreates_and_retires_record(tmp_settings):
    async with mocked({
        "orbio_get_balance": _balance(50.0),
        "orbio_get_key_status": _status(True, created_hours_ago=8 * 24),
        "orbio_create_key": _structured({
            "key": "sk-orb-NEW", "prefix": "sk-orbio-new1",
            "baseUrl": "b", "replaced": True}),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        await bot.state.save_key(KeyRecord(
            key_id="sk-orbio-ab12", secret="sk-old",
            headroom_usd=0.0, spend_usd=0.0,
            created_at=time.time() - 8 * 24 * 3600,
        ))
        report = await bot.tick()
        assert report.action.value == "create"

        keys = await bot.state.recent_keys(limit=10)
        old = next(k for k in keys if k.key_id == "sk-orbio-ab12")
        assert old.retired_at is not None
        cur = await bot.state.current_key()
        assert cur is not None and cur.key_id == "sk-orbio-new1"


@pytest.mark.asyncio
async def test_low_balance_alerts_with_key(tmp_settings):
    async with mocked({
        "orbio_get_balance": _balance(1.0),
        "orbio_get_key_status": _status(True, created_hours_ago=1.0),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        await bot.state.save_key(KeyRecord(
            key_id="sk-orbio-ab12", secret="sk-old",
            headroom_usd=0.0, spend_usd=0.0,
            created_at=time.time() - 3600,
        ))
        report = await bot.tick()
        assert report.action.value == "alert"
        events = await bot.state.recent_events(limit=5)
        assert any(e["kind"] == "balance_low" for e in events)


@pytest.mark.asyncio
async def test_legacy_key_triggers_delete(tmp_settings):
    from bagbot.orbio_mcp import KeyStatus
    status_payload = {
        "hasKey": True, "prefix": "sk-orbio-ab12",
        "createdAt": "2026-09-07T04:52:35Z", "lastUsedAt": None,
        "baseUrl": "https://api.orbio.so/api/v1",
        "legacy": {"prefix": "sk-or-v1-legacy", "headroom": 5.0},
    }
    async with mocked({
        "orbio_get_balance": _balance(50.0),
        "orbio_get_key_status": _structured(status_payload),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        await bot.state.save_key(KeyRecord(
            key_id="sk-orbio-ab12", secret="sk-old",
            headroom_usd=0.0, spend_usd=0.0,
            created_at=time.time() - 3600,
        ))
        # Sanity: our mock returns a KeyStatus with legacy set
        st = KeyStatus.from_payload(status_payload)
        assert st.legacy is not None
        # Drive _execute DELETE branch directly (policy layer tested elsewhere)
        from bagbot.policy import Action
        from bagbot.orbio_mcp import Balance as Bal
        bal = Bal(accrued_usd=50, purchased_usd=0, spent_usd=0,
                  claimed_usd=0, unclaimed_usd=50)
        await bot._execute(Action.DELETE, "legacy test",
                           await bot.state.current_key(), bal, st, bot.mcp)
        events = await bot.state.recent_events(limit=5)
        assert any(e["kind"] == "legacy_key_deleted" for e in events)


# ── Burn rate (balance curve IS the spend curve) ─────────────────────

@pytest.mark.asyncio
async def test_balance_drop_between_ticks_triggers_revoke_on_burst(tmp_settings):
    """Two ticks: balance falls $50 in ~50ms → ~$3.6M/h → leak guard revokes."""
    balances = [50.0, 0.0]
    async with mocked({
        "orbio_get_balance": _balance(balances[0]),
        "orbio_get_key_status": _status(True, created_hours_ago=1.0),
        "orbio_revoke_key": _structured({"revoked": True}),
    }) as mcp:
        bot = BagBot(tmp_settings)
        bot.mcp = mcp  # type: ignore[assignment]
        await bot.state.init()
        await bot.state.save_key(KeyRecord(
            key_id="sk-orbio-ab12", secret="sk-old",
            headroom_usd=0.0, spend_usd=0.0,
            created_at=time.time() - 3600,
        ))

        r1 = await bot.tick()
        assert r1.action.value == "nothing"  # baseline: no burn history

        # Second tick sees the balance drop (swap get_balance for one
        # that returns the lower balance).
        await asyncio.sleep(0.05)
        orig = mcp.get_balance

        async def second_balance():
            from bagbot.orbio_mcp import Balance
            return Balance.from_payload({
                "accrued": {"usd": 50.0, "microUsd": "50000000"},
                "balance": {"usd": 0.0, "microUsd": "0"},
            })
        mcp.get_balance = second_balance  # type: ignore[method-assign]
        try:
            r2 = await bot.tick()
        finally:
            mcp.get_balance = orig  # type: ignore[method-assign]

        assert r2.action.value == "revoke"
        cur = await bot.state.current_key()
        assert cur is None, "key should be retired after revoke"


@pytest.mark.asyncio
async def test_balance_increase_is_zero_burn(tmp_settings):
    """Accruals grow the balance — that must NOT look like negative burn."""
    bot = BagBot(tmp_settings)
    bot._last_balance_usd = 10.0
    bot._last_balance_ts = time.time() - 1.0
    rate = bot._compute_burn_rate(50.0)  # balance grew
    assert rate == 0.0


@pytest.mark.asyncio
async def test_burn_rate_zero_dt_returns_zero(tmp_settings):
    """dt == 0 (clock frozen) must return 0, never div-by-zero/Inf."""
    bot = BagBot(tmp_settings)
    bot._last_balance_usd = 10.0
    bot._last_balance_ts = 100.0
    fixed = 100.0
    real_time = time.time
    time.time = lambda: fixed
    try:
        rate = bot._compute_burn_rate(5.0)
    finally:
        time.time = real_time
    assert rate == 0.0


@pytest.mark.asyncio
async def test_burn_rate_first_sample_returns_zero(tmp_settings):
    bot = BagBot(tmp_settings)
    bot._last_balance_usd = None
    bot._last_balance_ts = 0.0
    assert bot._compute_burn_rate(42.0) == 0.0


# ── _execute branches (direct drive, new signature) ─────────────────

@pytest.mark.asyncio
async def test_action_alert_notifies(tmp_settings):
    from bagbot.policy import Action
    from unittest.mock import AsyncMock
    from bagbot.orbio_mcp import Balance as Bal

    bot = BagBot(tmp_settings)
    await bot.state.init()
    bot.notifier = AsyncMock()

    bal = Bal(accrued_usd=1.0, purchased_usd=0, spent_usd=0,
              claimed_usd=0, unclaimed_usd=0.5)
    await bot._execute(Action.ALERT, "test alert", None, bal, None,
                       bot.require_mcp())
    events = await bot.state.recent_events(limit=5)
    assert any(e["kind"] == "balance_low" for e in events)
    bot.notifier.notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_create_saves_secret_once(tmp_settings):
    from bagbot.policy import Action
    from unittest.mock import AsyncMock
    from bagbot.orbio_mcp import Balance as Bal, Key

    bot = BagBot(tmp_settings)
    await bot.state.init()
    bot.notifier = AsyncMock()

    class FakeMCP:
        async def create_key(self, label=None):
            return Key(secret="sk-orb-XYZ", prefix="sk-orbio-xy",
                       base_url="https://api.orbio.so/api/v1", replaced=False)

    bal = Bal(accrued_usd=10, purchased_usd=0, spent_usd=0,
              claimed_usd=0, unclaimed_usd=10)
    await bot._execute(Action.CREATE, "test create", None, bal, None, FakeMCP())
    cur = await bot.state.current_key()
    assert cur is not None
    assert cur.secret == "sk-orb-XYZ"
    events = await bot.state.recent_events(limit=5)
    assert any(e["kind"] == "key_created" for e in events)
