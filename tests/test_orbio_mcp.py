"""Tests for the Orbio MCP client — live gateway API (5 tools).

Uses httpx MockTransport to exercise the JSON-RPC wrapping, live payload
parsing ({"usd": x, "microUsd": "y"} dicts, ISO timestamps), error
handling, and retries.  Payload shapes mirror what orbio.so actually
returned on 2026-09-08.
"""

import json
from contextlib import asynccontextmanager

import pytest
import httpx

from bagbot.orbio_mcp import (
    Balance,
    DeleteResult,
    Key,
    KeyStatus,
    OrbioMCPClient,
    OrbioMCPError,
    RevokeResult,
    _usd,
)


def _mcp_ok(result: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": result},
    )


def _mcp_error(message: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": message}},
    )


@asynccontextmanager
async def mock_client(handler, **kw):
    """OrbioMCPClient whose transport is a MockTransport(handler).

    We set ``_client`` directly and skip ``__aenter__`` — otherwise the
    real httpx client would be rebuilt and attempts would hit the network.
    """
    c = OrbioMCPClient("https://x.example/mcp", "tok", **kw)
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=c.endpoint,
        headers={"Authorization": f"Bearer {c.token}"},
    )
    try:
        yield c
    finally:
        await c._client.aclose()


# ── _usd coercion (live amounts are {usd, microUsd} dicts) ───────────

def test_usd_from_dict_with_usd():
    assert _usd({"usd": 100, "microUsd": "100000000"}) == 100.0


def test_usd_from_dict_micro_only():
    assert _usd({"microUsd": "1500000"}) == 1.5


def test_usd_from_dict_usd_takes_precedence():
    assert _usd({"usd": 2, "microUsd": "999999"}) == 2.0


def test_usd_from_number():
    assert _usd(7.5) == 7.5


def test_usd_from_none_and_garbage():
    assert _usd(None) == 0.0
    assert _usd("not-a-number") == 0.0
    assert _usd({}) == 0.0


# ── Balance parsing (live schema) ────────────────────────────────────

def test_balance_from_live_payload():
    bal = Balance.from_payload({
        "wallets": ["0xc2893"],
        "accrued": {"usd": 100, "microUsd": "100000000"},
        "purchased": {"usd": 0, "microUsd": "0"},
        "spent": {"usd": 5, "microUsd": "5000000"},
        "claimed": {"usd": 0, "microUsd": "0"},
        "balance": {"usd": 95, "microUsd": "95000000"},
    })
    assert bal.accrued_usd == 100.0
    assert bal.spent_usd == 5.0
    assert bal.unclaimed_usd == 95.0
    assert bal.wallets == ["0xc2893"]


def test_balance_missing_fields_default_zero():
    bal = Balance.from_payload({})
    assert bal.accrued_usd == 0.0
    assert bal.unclaimed_usd == 0.0


# ── KeyStatus parsing (live schema) ──────────────────────────────────

def test_keystatus_from_live_payload():
    st = KeyStatus.from_payload({
        "hasKey": True,
        "prefix": "sk-orbio-xHtDY5",
        "createdAt": "2026-09-07T04:52:35.390808+00:00",
        "lastUsedAt": None,
        "baseUrl": "https://api.orbio.so/api/v1",
        "legacy": None,
    })
    assert st.has_key is True
    assert st.prefix == "sk-orbio-xHtDY5"
    assert st.created_at is not None and st.created_at > 1_700_000_000
    assert st.last_used_at is None
    assert st.base_url == "https://api.orbio.so/api/v1"


def test_keystatus_no_key():
    st = KeyStatus.from_payload({"hasKey": False, "prefix": None,
                                 "createdAt": None, "lastUsedAt": None,
                                 "baseUrl": "", "legacy": None})
    assert st.has_key is False


def test_keystatus_garbage_timestamp_is_none():
    st = KeyStatus.from_payload({"hasKey": True, "createdAt": "not-a-date"})
    assert st.created_at is None


# ── Tool calls (JSON-RPC over mock transport) ────────────────────────

@pytest.mark.asyncio
async def test_get_balance_parses_structured_content():
    def handler(req):
        return _mcp_ok({"structuredContent": {
            "wallets": ["0xa"],
            "accrued": {"usd": 12.34, "microUsd": "12340000"},
            "purchased": {"usd": 0, "microUsd": "0"},
            "spent": {"usd": 1, "microUsd": "1000000"},
            "claimed": {"usd": 0, "microUsd": "0"},
            "balance": {"usd": 11.34, "microUsd": "11340000"},
        }})
    async with mock_client(handler) as c:
        bal = await c.get_balance()
    assert bal.accrued_usd == 12.34
    assert bal.unclaimed_usd == 11.34


@pytest.mark.asyncio
async def test_get_key_status_sends_no_args():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content.decode())
        return _mcp_ok({"structuredContent": {"hasKey": False}})
    async with mock_client(handler) as c:
        st = await c.get_key_status()
    assert st.has_key is False
    assert seen["body"]["params"]["arguments"] == {}
    assert seen["body"]["params"]["name"] == "orbio_get_key_status"


@pytest.mark.asyncio
async def test_create_key_returns_secret_and_prefix():
    def handler(req):
        return _mcp_ok({"structuredContent": {
            "key": "sk-orbio-SECRET-abcdef123456",
            "prefix": "sk-orbio-ab12",
            "baseUrl": "https://api.orbio.so/api/v1",
            "replaced": False,
        }})
    async with mock_client(handler) as c:
        key = await c.create_key(label="my-box")
    assert isinstance(key, Key)
    assert key.secret == "sk-orbio-SECRET-abcdef123456"
    assert key.prefix == "sk-orbio-ab12"
    assert key.replaced is False


@pytest.mark.asyncio
async def test_create_key_label_truncated_to_60():
    seen = {}

    def handler(req):
        seen["args"] = json.loads(req.content.decode())["params"]["arguments"]
        return _mcp_ok({"structuredContent": {"key": "k", "prefix": "p",
                                              "baseUrl": "b", "replaced": True}})
    async with mock_client(handler) as c:
        key = await c.create_key(label="x" * 100)
    assert len(seen["args"]["label"]) == 60
    assert key.replaced is True


@pytest.mark.asyncio
async def test_create_key_no_label_sends_empty_args():
    seen = {}

    def handler(req):
        seen["args"] = json.loads(req.content.decode())["params"]["arguments"]
        return _mcp_ok({"structuredContent": {"key": "k", "prefix": "p",
                                              "baseUrl": "b", "replaced": False}})
    async with mock_client(handler) as c:
        await c.create_key()
    assert seen["args"] == {}


@pytest.mark.asyncio
async def test_revoke_key():
    def handler(req):
        return _mcp_ok({"structuredContent": {"revoked": True}})
    async with mock_client(handler) as c:
        res = await c.revoke_key()
    assert isinstance(res, RevokeResult)
    assert res.revoked is True


@pytest.mark.asyncio
async def test_revoke_key_no_key_returns_false():
    def handler(req):
        return _mcp_ok({"structuredContent": {"revoked": False}})
    async with mock_client(handler) as c:
        res = await c.revoke_key()
    assert res.revoked is False


@pytest.mark.asyncio
async def test_delete_key_returns_refund():
    def handler(req):
        return _mcp_ok({"structuredContent": {
            "refunded": {"usd": 3.25, "microUsd": "3250000"},
            "label": "old-key",
        }})
    async with mock_client(handler) as c:
        res = await c.delete_key()
    assert isinstance(res, DeleteResult)
    assert res.refunded_usd == 3.25
    assert res.label == "old-key"


@pytest.mark.asyncio
async def test_delete_key_zero_refund_shape():
    def handler(req):
        return _mcp_ok({"structuredContent": {
            "refunded": {"usd": 0, "microUsd": "0"}, "label": None}})
    async with mock_client(handler) as c:
        res = await c.delete_key()
    assert res.refunded_usd == 0.0
    assert res.label is None


# ── Errors / transport behaviours ────────────────────────────────────

@pytest.mark.asyncio
async def test_posts_absolute_endpoint_without_trailing_slash():
    """Regression: httpx base_url + post('') used to add a trailing slash,
    and Orbio 308-redirects /api/mcp/ → /api/mcp which breaks POST.
    """
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return _mcp_ok({"structuredContent": {"hasKey": False}})
    async with mock_client(handler) as c:
        await c.get_key_status()
    assert seen["url"] == "https://x.example/mcp"
    assert not seen["url"].endswith("/")


@pytest.mark.asyncio
async def test_mcp_error_surfaced_with_tool_name():
    def handler(req):
        return _mcp_error("rate limit hit")
    async with mock_client(handler, max_retries=1) as c:
        with pytest.raises(OrbioMCPError) as exc:
            await c.get_balance()
        assert exc.value.tool == "orbio_get_balance"
        assert "rate limit" in str(exc.value)


@pytest.mark.asyncio
async def test_unknown_tool_error_surfaces():
    """Regression: real server sent -32601 Unknown tool for the old 6-tool
    names.  The client must surface JSON-RPC errors, not swallow them."""
    def handler(req):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {
            "code": -32601, "message": "Unknown tool: orbio_claim_key"}})
    async with mock_client(handler, max_retries=1) as c:
        with pytest.raises(OrbioMCPError) as exc:
            await c._call("orbio_claim_key")
        assert "-32601" in str(exc.value) or "Unknown tool" in str(exc.value)


@pytest.mark.asyncio
async def test_5xx_triggers_retry_then_gives_up():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="server overloaded")
    async with mock_client(handler, max_retries=2) as c:
        with pytest.raises(OrbioMCPError):
            await c.get_balance()
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_429_respects_retry_after():
    state = {"calls": 0}

    def handler(req):
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, text="slow down",
                                  headers={"retry-after": "0"})
        return _mcp_ok({"structuredContent": {
            "accrued": {"usd": 1, "microUsd": "1000000"},
            "balance": {"usd": 1, "microUsd": "1000000"}}})
    async with mock_client(handler, max_retries=3) as c:
        bal = await c.get_balance()
    assert state["calls"] == 2
    assert bal.unclaimed_usd == 1


@pytest.mark.asyncio
async def test_freetext_content_response_parsed():
    """When the server returns content[].text with a JSON string instead
    of structuredContent."""
    def handler(req):
        return _mcp_ok({"content": [{"type": "text", "text": json.dumps(
            {"hasKey": True, "prefix": "sk-orbio-zz", "baseUrl": "b",
             "createdAt": None, "lastUsedAt": None, "legacy": None}
        )}]})
    async with mock_client(handler) as c:
        st = await c.get_key_status()
    assert st.has_key is True
    assert st.prefix == "sk-orbio-zz"


@pytest.mark.asyncio
async def test_client_requires_token():
    with pytest.raises(ValueError, match="token"):
        OrbioMCPClient("https://x.example/mcp", "")


@pytest.mark.asyncio
async def test_client_requires_endpoint():
    with pytest.raises(ValueError, match="endpoint"):
        OrbioMCPClient("", "tok")


@pytest.mark.asyncio
async def test_endpoint_trailing_slash_normalised():
    c = OrbioMCPClient("https://x.example/mcp/", "tok")
    assert c.endpoint == "https://x.example/mcp"


@pytest.mark.asyncio
async def test_4xx_fails_fast_without_retry():
    """Regression (found live): a 401 expired-token response is
    deterministic — 3 retries with back-off just wasted ~14s and made
    'token expired' look like a flaky network. 4xx must fail on the
    first attempt."""
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="Unauthorized")
    async with mock_client(handler, max_retries=3) as c:
        with pytest.raises(OrbioMCPError) as exc:
            await c.get_balance()
    assert calls["n"] == 1, "4xx must not be retried"
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_5xx_still_retries():
    """Server-side 5xx stays retryable — only 4xx skips the loop."""
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="overloaded")
    async with mock_client(handler, max_retries=3) as c:
        with pytest.raises(OrbioMCPError):
            await c.get_balance()
    assert calls["n"] == 3
