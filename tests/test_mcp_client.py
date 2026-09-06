"""Tests for the Orbio MCP client — uses a fake transport (httpx MockTransport)
to exercise the JSON-RPC wrapping, error handling, and tool methods.
"""

import json
import pytest
import httpx

from bagbot.orbio_mcp import (
    Balance, Key, KeyStatus, OrbioMCPClient, OrbioMCPError,
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


@pytest.mark.asyncio
async def test_get_balance_parses_structured_content():
    transport = httpx.MockTransport(lambda req: _mcp_ok({
        "structuredContent": {
            "earned": 12.34, "claimed": 5.0, "unclaimed": 7.34, "currency": "USD"
        }
    }))
    async with OrbioMCPClient("https://x.example/mcp", "tok") as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        bal = await c.get_balance()
    assert bal.earned_usd == 12.34
    assert bal.claimed_usd == 5.0
    assert bal.unclaimed_usd == 7.34


@pytest.mark.asyncio
async def test_claim_key_caps_input():
    """claim_key should reject out-of-range caps."""
    async with OrbioMCPClient("https://x.example/mcp", "tok") as c:
        c._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _mcp_ok({})),
                                       base_url=c.endpoint)
        with pytest.raises(ValueError):
            await c.claim_key(cap_usd=0)
        with pytest.raises(ValueError):
            await c.claim_key(cap_usd=201)


@pytest.mark.asyncio
async def test_mcp_error_surfaced_with_tool_name():
    async def handler(req):
        return _mcp_error("rate limit hit")
    transport = httpx.MockTransport(handler)
    async with OrbioMCPClient("https://x.example/mcp", "tok", max_retries=1) as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        with pytest.raises(OrbioMCPError) as exc:
            await c.get_balance()
        assert exc.value.tool == "orbio_get_balance"
        assert "rate limit" in str(exc.value)


@pytest.mark.asyncio
async def test_5xx_triggers_retry_then_gives_up():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="server overloaded")
    transport = httpx.MockTransport(handler)
    async with OrbioMCPClient("https://x.example/mcp", "tok", max_retries=2) as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        with pytest.raises(OrbioMCPError):
            await c.get_balance()
    # Should have tried max_retries times
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_429_respects_retry_after():
    """429 with retry_after header should sleep, then succeed."""
    state = {"calls": 0}

    def handler(req):
        state["calls"] += 1
        if state["calls"] == 1:
            r = httpx.Response(429, text="slow down",
                               headers={"retry-after": "0"})
            return r
        return _mcp_ok({"structuredContent": {"earned": 1, "claimed": 0, "unclaimed": 1}})

    transport = httpx.MockTransport(handler)
    async with OrbioMCPClient("https://x.example/mcp", "tok", max_retries=3) as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        bal = await c.get_balance()
    assert state["calls"] == 2
    assert bal.unclaimed_usd == 1


@pytest.mark.asyncio
async def test_freetext_content_response_parsed():
    """When the server returns content[].text with a JSON string."""
    transport = httpx.MockTransport(lambda req: _mcp_ok({
        "content": [{"type": "text", "text": json.dumps(
            {"earned": 3, "claimed": 1, "unclaimed": 2, "currency": "USD"}
        )}]
    }))
    async with OrbioMCPClient("https://x.example/mcp", "tok") as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        bal = await c.get_balance()
    assert bal.unclaimed_usd == 2


@pytest.mark.asyncio
async def test_get_balance_then_claim():
    """Sanity: get_balance returns a Balance; subsequent claim returns a Key."""
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            return _mcp_ok({"structuredContent":
                             {"earned": 10, "claimed": 0, "unclaimed": 10}})
        return _mcp_ok({"key_id": "k_new", "secret": "sk-1", "headroom": 200.0})

    transport = httpx.MockTransport(handler)
    async with OrbioMCPClient("https://x.example/mcp", "tok") as c:
        c._client = httpx.AsyncClient(transport=transport, base_url=c.endpoint,
                                       headers={"Authorization": f"Bearer {c.token}"})
        bal = await c.get_balance()
        assert bal.unclaimed_usd == 10
        key = await c.claim_key(cap_usd=10)
        assert key.key_id == "k_new"
        assert key.headroom_usd == 200.0


@pytest.mark.asyncio
async def test_client_requires_token():
    with pytest.raises(ValueError, match="token"):
        OrbioMCPClient("https://x.example/mcp", "")


@pytest.mark.asyncio
async def test_client_requires_endpoint():
    with pytest.raises(ValueError, match="endpoint"):
        OrbioMCPClient("", "tok")
