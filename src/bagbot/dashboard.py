"""BagBot dashboard — FastAPI web UI in Chinese.

Endpoints:
  GET  /                 — Chinese dashboard
  GET  /api/state        — JSON snapshot (for polling)
  GET  /api/events       — JSON event log
  GET  /api/balances     — JSON balance history (for sparkline)
  POST /api/create       — mint (or rotate) the key manually
  POST /api/revoke       — stop the key manually
  POST /api/claim        — alias of /api/create (back-compat)
  POST /api/rotate       — alias of /api/create (back-compat)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings
from .daemon import BagBot
from .state import KeyRecord
from .orbio_mcp import OrbioMCPError

log = logging.getLogger("bagbot.dashboard")

_DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
_TEMPLATES = Jinja2Templates(directory=str(_DASHBOARD_DIR / "templates"))


def _require_dashboard_token(
    settings: Settings,
    authorization: str | None = Header(default=None),
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
) -> None:
    """Protect mutating endpoints.

    - If DASHBOARD_TOKEN is empty → mutations are disabled (403).
    - Accept either ``Authorization: Bearer <token>`` or ``X-Dashboard-Token: <token>``.
    """
    expected = (settings.dashboard.token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail=(
                "Dashboard mutations disabled. "
                "Set DASHBOARD_TOKEN in .env to enable claim/rotate/topup."
            ),
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_dashboard_token:
        provided = x_dashboard_token.strip()
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="invalid or missing dashboard token")


def build_app(bot: BagBot, settings: Settings) -> FastAPI:
    app = FastAPI(
        title="BagBot Dashboard",
        description="BagBot — 你的 Agent 自己管钱",
        version="0.1.0",
    )

    # Static (CSS / JS / favicon).
    static_dir = _DASHBOARD_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def _auth(
        authorization: str | None = Header(default=None),
        x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
    ) -> None:
        _require_dashboard_token(settings, authorization, x_dashboard_token)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        last = bot.last_tick
        cur = None
        if last is not None:
            cur = {
                "ts": last.ts,
                "balance": last.balance.unclaimed_usd,
                "earned": last.balance.accrued_usd,
                "claimed": last.balance.claimed_usd,
                "action": last.action.value,
                "reason": last.reason,
                "key_prefix": last.status.prefix if last.status else None,
                "has_key": last.status.has_key if last.status else False,
                "base_url": last.status.base_url if last.status else None,
            }
        # Starlette ≥ 0.27 / FastAPI ≥ 0.110: signature is
        #   TemplateResponse(request, name, context)
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "wallet_label": settings.wallet_label,
                "wallet": settings.orbio_wallet,
                "low_balance": settings.low_balance_usd,
                "rotate_max_age": settings.rotate_max_age_hours,
                "current": cur,
            },
        )

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        last = bot.last_tick
        if last is None:
            return {"status": "no_tick_yet", "ts": time.time()}
        return {
            "status": "ok",
            "ts": last.ts,
            "balance": {
                "accrued_usd": last.balance.accrued_usd,
                "claimed_usd": last.balance.claimed_usd,
                "spent_usd": last.balance.spent_usd,
                "unclaimed_usd": last.balance.unclaimed_usd,
            },
            "action": last.action.value,
            "reason": last.reason,
            "key": (
                {
                    "has_key": last.status.has_key,
                    "prefix": last.status.prefix,
                    "base_url": last.status.base_url,
                    "created_at": last.status.created_at,
                    "last_used_at": last.status.last_used_at,
                }
                if last.status
                else None
            ),
        }

    @app.get("/api/events")
    async def events(limit: int = 50) -> list[dict[str, Any]]:
        return await bot.state.recent_events(limit=min(limit, 200))

    @app.get("/api/balances")
    async def balances(limit: int = 100) -> list[dict[str, Any]]:
        return await bot.state.recent_balances(limit=min(limit, 500))

    async def _create_key_response() -> dict[str, Any]:
        try:
            mcp = bot.require_mcp()
            async with mcp:
                key = await mcp.create_key(label=settings.wallet_label)
        except OrbioMCPError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        await bot.state.retire_all_active(reason="manual re-create via dashboard")
        await bot.state.save_key(KeyRecord(
            key_id=key.prefix, secret=key.secret,
            headroom_usd=0.0, spend_usd=0.0, created_at=time.time(),
        ))
        # Never return the secret to the browser.
        return {"prefix": key.prefix, "base_url": key.base_url,
                "replaced": key.replaced}

    @app.post("/api/create")
    async def create(_: None = Depends(_auth)):
        return await _create_key_response()

    # Back-compat aliases: in the gateway model rotate == create (atomic
    # replacement), and topup no longer exists — the key spends the balance.
    @app.post("/api/claim")
    @app.post("/api/rotate")
    async def claim_or_rotate(_: None = Depends(_auth)):
        return await _create_key_response()

    @app.post("/api/revoke")
    async def revoke(_: None = Depends(_auth)):
        try:
            mcp = bot.require_mcp()
            async with mcp:
                result = await mcp.revoke_key()
        except OrbioMCPError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        cur = await bot.state.current_key()
        if cur is not None:
            await bot.state.retire_key(cur.key_id, reason="manual revoke via dashboard")
        return {"revoked": result.revoked}

    return app


async def run_dashboard(bot: BagBot, settings: Settings) -> None:
    """Serve the dashboard inside the already-running asyncio loop.

    ``uvicorn.run()`` would try to create its own event loop, which raises
    "Cannot run the event loop while another loop is running" when called
    from ``cli.cmd_dashboard`` (already inside ``asyncio.run``).  Building
    a ``uvicorn.Server`` and awaiting ``serve()`` reuses the current loop.
    """
    import uvicorn

    app = build_app(bot, settings)
    config = uvicorn.Config(
        app,
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
