"""Orbio MCP client — async wrapper around the 6 tools.

Spec source: https://orbio.so/mcp
Tools:
  orbio_get_balance      — return unclaimed credits (USD)
  orbio_claim_key        — mint an OpenRouter key, up to KEY_CAP_USD
  orbio_get_key_status   — live key spend (from OpenRouter)
  orbio_top_up_key       — move balance onto existing key (no secret change)
  orbio_rotate_key       — fresh secret, same credits, old key dies
  orbio_delete_key       — kill key, unspent returns to balance

The MCP server is exposed by Orbio as a remote HTTP endpoint using
Streamable HTTP transport.  We use a tiny JSON-RPC over HTTP wrapper
compatible with the MCP "tools/call" shape.  If the official transport
differs in your environment, point ORBIO_MCP_URL at a local proxy and
keep the same payload shape — only `BaseMCPClient._request` would need
to change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("bagbot.orbio_mcp")


# ── Typed responses ────────────────────────────────────────────────────────

@dataclass
class Balance:
    """Result of orbio_get_balance."""
    earned_usd: float
    claimed_usd: float
    unclaimed_usd: float
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> Balance:
        return cls(
            earned_usd=float(p.get("earned", 0.0)),
            claimed_usd=float(p.get("claimed", 0.0)),
            unclaimed_usd=float(p.get("unclaimed", 0.0)),
            currency=p.get("currency", "USD"),
            raw=p,
        )


@dataclass
class Key:
    """An issued OpenRouter key."""
    key_id: str
    secret: str            # the sk-or-v1-… secret
    headroom_usd: float    # how much can still be spent on this key
    spend_usd: float = 0.0
    created_at: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def used_fraction(self) -> float:
        cap = self.headroom_usd + self.spend_usd
        if cap <= 0:
            return 0.0
        return self.spend_usd / cap


@dataclass
class KeyStatus:
    """Live key status read from OpenRouter via the MCP."""
    key_id: str
    spend_usd: float
    headroom_usd: float
    remaining_usd: float
    last_used_at: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def used_fraction(self) -> float:
        """Fraction of the original cap that has been spent."""
        cap = self.headroom_usd + self.spend_usd
        if cap <= 0:
            return 0.0
        return self.spend_usd / cap

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> KeyStatus:
        spend = float(p.get("spend", 0.0))
        headroom = float(p.get("headroom", 0.0))
        return cls(
            key_id=p.get("key_id", ""),
            spend_usd=spend,
            headroom_usd=headroom,
            remaining_usd=float(p.get("remaining", headroom - spend)),
            last_used_at=p.get("last_used_at"),
            raw=p,
        )


# ── Errors ────────────────────────────────────────────────────────────────

class OrbioMCPError(RuntimeError):
    """Generic Orbio MCP error."""
    def __init__(self, tool: str, message: str, payload: dict | None = None):
        super().__init__(f"[{tool}] {message}")
        self.tool = tool
        self.payload = payload or {}


# ── Client ────────────────────────────────────────────────────────────────

class OrbioMCPClient:
    """Async client for the 6 Orbio MCP tools.

    Backed by httpx; safe to share across coroutines.
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        if not endpoint:
            raise ValueError("Orbio MCP endpoint required")
        if not token:
            raise ValueError("Orbio MCP bearer token required")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OrbioMCPClient:
        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Low-level transport ────────────────────────────────────────────

    async def _call(self, tool: str, arguments: dict | None = None) -> dict:
        """Issue a JSON-RPC 2.0 tools/call request.

        Most MCP servers accept POST {endpoint} with a body of:
          {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "<tool>", "arguments": {...}}}
        We retry on transient errors (5xx, network) and respect
        server-supplied retry_after hints.
        """
        assert self._client is not None, "use as async context manager"
        arguments = arguments or {}
        body = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 10_000,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self._client.post("", json=body)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("retry-after", "1"))
                    log.warning("rate-limited on %s, sleeping %.1fs", tool, retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status_code >= 500:
                    raise OrbioMCPError(tool, f"server {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise OrbioMCPError(tool, str(data["error"]), data["error"])
                # MCP returns the result under "result"; structured content is in
                # result.structuredContent for typed outputs, or result.content[].text
                # for freeform.  We try both.
                result = data.get("result", data)
                if isinstance(result, dict):
                    if "structuredContent" in result:
                        return result["structuredContent"]
                    content = result.get("content")
                    if isinstance(content, list) and content:
                        # take the first text part
                        first = content[0]
                        if isinstance(first, dict) and "text" in first:
                            try:
                                return json.loads(first["text"])
                            except json.JSONDecodeError:
                                return {"text": first["text"]}
                return result if isinstance(result, dict) else {"value": result}
            except (httpx.HTTPError, OrbioMCPError) as e:
                last_err = e
                wait = min(2 ** attempt, 30)
                log.warning("attempt %d/%d on %s failed: %s; retrying in %.1fs",
                            attempt, self.max_retries, tool, e, wait)
                await asyncio.sleep(wait)
        raise OrbioMCPError(tool, f"giving up after {self.max_retries} retries: {last_err}")

    # ── Public tools ──────────────────────────────────────────────────

    async def get_balance(self) -> Balance:
        """orbio_get_balance — how many unclaimed credits you have right now."""
        p = await self._call("orbio_get_balance", {})
        return Balance.from_payload(p)

    async def claim_key(self, cap_usd: float = 200.0) -> Key:
        """orbio_claim_key — mint a fresh OpenRouter key funded up to cap_usd."""
        if cap_usd <= 0 or cap_usd > 200.0:
            raise ValueError("cap_usd must be in (0, 200]")
        p = await self._call("orbio_claim_key", {"cap_usd": cap_usd})
        return Key(
            key_id=p.get("key_id", ""),
            secret=p.get("secret", ""),
            headroom_usd=float(p.get("headroom", cap_usd)),
            raw=p,
        )

    async def get_key_status(self, key_id: str) -> KeyStatus:
        """orbio_get_key_status — live key spend (sourced from OpenRouter)."""
        p = await self._call("orbio_get_key_status", {"key_id": key_id})
        return KeyStatus.from_payload(p)

    async def top_up_key(self, key_id: str, amount_usd: float) -> Key:
        """orbio_top_up_key — move more balance onto the same key. Secret unchanged."""
        p = await self._call(
            "orbio_top_up_key", {"key_id": key_id, "amount_usd": amount_usd}
        )
        return Key(
            key_id=p.get("key_id", key_id),
            secret=p.get("secret", ""),
            headroom_usd=float(p.get("headroom", 0.0)),
            spend_usd=float(p.get("spend", 0.0)),
            raw=p,
        )

    async def rotate_key(self, key_id: str) -> Key:
        """orbio_rotate_key — fresh secret on the same credit. Old secret dies first."""
        p = await self._call("orbio_rotate_key", {"key_id": key_id})
        return Key(
            key_id=p.get("key_id", key_id),
            secret=p.get("secret", ""),
            headroom_usd=float(p.get("headroom", 0.0)),
            raw=p,
        )

    async def delete_key(self, key_id: str) -> None:
        """orbio_delete_key — kill the key. Whatever wasn't spent comes back to balance."""
        await self._call("orbio_delete_key", {"key_id": key_id})

    # ── Convenience: high-level flow ─────────────────────────────────

    async def ensure_key(
        self,
        *,
        current_key_id: str | None,
        cap_usd: float,
        low_balance_threshold_usd: float,
    ) -> tuple[Key, str]:
        """Return (key, action) where action ∈ {"claimed","reused","topped_up","rotated"}.

        This is the high-level helper the daemon calls once per tick.
        """
        bal = await self.get_balance()

        if current_key_id is None:
            if bal.unclaimed_usd < low_balance_threshold_usd:
                # Not enough to even claim — caller will wait and retry.
                return (None, "insufficient_balance")  # type: ignore[return-value]
            key = await self.claim_key(cap_usd=cap_usd)
            return (key, "claimed")

        # We have a key — check its status.
        status = await self.get_key_status(current_key_id)
        if status.remaining_usd <= 0:
            # Out of headroom.  Try to top up from unclaimed; if not enough, rotate.
            if bal.unclaimed_usd >= cap_usd:
                key = await self.top_up_key(current_key_id, cap_usd)
                return (key, "topped_up")
            key = await self.rotate_key(current_key_id)
            return (key, "rotated_depleted")

        return (Key(  # reuse the existing one
            key_id=status.key_id,
            secret="",  # secret not re-fetched — we keep using what we had
            headroom_usd=status.remaining_usd,
            spend_usd=status.spend_usd,
        ), "reused")
