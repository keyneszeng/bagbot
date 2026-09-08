"""Orbio MCP client — async wrapper around the live Orbio gateway API.

Spec source: https://orbio.so/mcp  (live schema verified 2026-09-08 via
``tools/list`` against https://www.orbio.so/api/mcp)

The real API exposes **5 tools** (not the 6 from the early draft docs) and
works on a *gateway* model:

  orbio_get_balance    — accrued / purchased / spent / claimed / balance (USD)
  orbio_get_key_status — hasKey, prefix, createdAt, lastUsedAt, baseUrl, legacy
  orbio_create_key     — mint the key (secret shown once); replaces an
                         existing key atomically (this is the "rotate")
  orbio_revoke_key     — stop the key; balance untouched, nothing refunded
  orbio_delete_key     — legacy pre-gateway OpenRouter key cleanup + refund

Key model differences from the draft:
  * the key has **no cap** — it spends the live balance, request by request;
  * there is **no top-up** — the gateway draws on the account balance;
  * "rotation" is just ``orbio_create_key`` again (old key retired in the
    same statement, ``replaced: true``);
  * ``unclaimed`` (spendable) = ``balance.usd`` — the balance IS the quota.

Response amounts arrive as ``{"usd": float, "microUsd": "int-str"}`` dicts;
``_usd`` coerces either shape (and bare numbers) into float USD.
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

def _usd(value: Any) -> float:
    """Coerce an Orbio amount (dict/number/None) into float USD."""
    if isinstance(value, dict):
        usd = value.get("usd")
        if usd is not None:
            return float(usd)
        micro = value.get("microUsd")
        if micro is not None:
            return float(micro) / 1_000_000.0
        return 0.0
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ts(value: Any) -> float | None:
    """Parse an ISO timestamp (or epoch) into epoch seconds; None if absent."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


@dataclass
class Balance:
    """Result of orbio_get_balance (live schema)."""

    accrued_usd: float      # lifetime credits earned from holding $ORBIO
    purchased_usd: float    # credits bought outright
    spent_usd: float        # spent through the gateway
    claimed_usd: float      # (legacy) claimed onto a provisioned key
    unclaimed_usd: float    # spendable now == balance.usd
    wallets: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> Balance:
        return cls(
            accrued_usd=_usd(p.get("accrued", 0.0)),
            purchased_usd=_usd(p.get("purchased", 0.0)),
            spent_usd=_usd(p.get("spent", 0.0)),
            claimed_usd=_usd(p.get("claimed", 0.0)),
            unclaimed_usd=_usd(p.get("balance", 0.0)),
            wallets=list(p.get("wallets", []) or []),
            raw=p,
        )


@dataclass
class KeyStatus:
    """Result of orbio_get_key_status (live schema)."""

    has_key: bool
    prefix: str | None = None        # visible head, e.g. sk-orbio-ab12
    created_at: float | None = None  # epoch seconds
    last_used_at: float | None = None
    base_url: str | None = None      # OpenAI-compatible endpoint to pair with
    legacy: dict[str, Any] | None = None  # pre-gateway OpenRouter key, if any
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> KeyStatus:
        return cls(
            has_key=bool(p.get("hasKey", False)),
            prefix=p.get("prefix"),
            created_at=_ts(p.get("createdAt")),
            last_used_at=_ts(p.get("lastUsedAt")),
            base_url=p.get("baseUrl"),
            legacy=p.get("legacy"),
            raw=p,
        )


@dataclass
class Key:
    """Result of orbio_create_key.  The secret is shown exactly once."""

    secret: str                      # full sk-orbio-… secret (store immediately)
    prefix: str = ""                 # visible head for display/identification
    base_url: str = ""               # OpenAI-compatible base URL
    replaced: bool = False           # True when an old key was retired
    created_at: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RevokeResult:
    """Result of orbio_revoke_key."""

    revoked: bool                    # False when there was no key to revoke
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeleteResult:
    """Result of orbio_delete_key (legacy cleanup)."""

    refunded_usd: float
    label: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> DeleteResult:
        return cls(
            refunded_usd=_usd(p.get("refunded", 0.0)),
            label=p.get("label"),
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
    """Async client for the live Orbio gateway MCP (5 tools).

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
                "Accept": "application/json, text/event-stream",
            },
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Low-level transport ────────────────────────────────────────────

    async def _call(self, tool: str, arguments: dict | None = None) -> dict:
        """Issue a JSON-RPC 2.0 tools/call request with retries."""
        assert self._client is not None, "use as async context manager"
        body = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 10_000,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        }
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # POST the absolute endpoint URL. Using post("") with
                # base_url makes httpx join to "<base>/" (trailing slash),
                # which Orbio 308-redirects back to the slash-less path —
                # and httpx refuses to re-POST across redirects.
                resp = await self._client.post(self.endpoint, json=body)
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
                result = data.get("result", data)
                if isinstance(result, dict):
                    if "structuredContent" in result:
                        return result["structuredContent"]
                    content = result.get("content")
                    if isinstance(content, list) and content:
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

    # ── Public tools (live API, 5 tools) ──────────────────────────────

    async def get_balance(self) -> Balance:
        """orbio_get_balance — live credit picture; balance IS the quota."""
        p = await self._call("orbio_get_balance", {})
        return Balance.from_payload(p)

    async def get_key_status(self) -> KeyStatus:
        """orbio_get_key_status — whether a key exists + metadata.

        Takes no arguments in the live API (it is per-account, not per-key).
        """
        p = await self._call("orbio_get_key_status", {})
        return KeyStatus.from_payload(p)

    async def create_key(self, label: str | None = None) -> Key:
        """orbio_create_key — mint the key; secret shown exactly once.

        If a key already exists it is retired in the same statement
        (``replaced: true``), so this is also the rotation / leak response.
        There is no amount to choose — the key draws on the live balance.
        """
        args: dict[str, Any] = {}
        if label:
            args["label"] = label[:60]
        p = await self._call("orbio_create_key", args)
        return Key(
            secret=p.get("key", ""),
            prefix=p.get("prefix", ""),
            base_url=p.get("baseUrl", ""),
            replaced=bool(p.get("replaced", False)),
            raw=p,
        )

    async def revoke_key(self) -> RevokeResult:
        """orbio_revoke_key — stop the key; balance untouched."""
        p = await self._call("orbio_revoke_key", {})
        return RevokeResult(revoked=bool(p.get("revoked", False)), raw=p)

    async def delete_key(self) -> DeleteResult:
        """orbio_delete_key — legacy pre-gateway OpenRouter key cleanup.

        Returns unspent credit to the account balance.  No-op for accounts
        that never provisioned a legacy key.
        """
        p = await self._call("orbio_delete_key", {})
        return DeleteResult.from_payload(p)
