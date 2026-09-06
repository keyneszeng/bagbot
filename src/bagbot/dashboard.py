"""BagBot dashboard — FastAPI web UI in Chinese.

Endpoints:
  GET  /                 — Chinese dashboard
  GET  /api/state        — JSON snapshot (for polling)
  GET  /api/events       — JSON event log
  GET  /api/balances     — JSON balance history (for sparkline)
  POST /api/claim        — manual force-claim
  POST /api/rotate       — manual force-rotate
  POST /api/topup        — manual top-up {amount}
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import Settings
from .daemon import BagBot
from .orbio_mcp import OrbioMCPError

log = logging.getLogger("bagbot.dashboard")

_DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
_TEMPLATES = Jinja2Templates(directory=str(_DASHBOARD_DIR / "templates"))


class TopUpBody(BaseModel):
    amount: float


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

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        last = bot.last_tick
        cur = None
        if last is not None:
            cur = {
                "ts": last.ts,
                "balance": last.balance.unclaimed_usd,
                "earned": last.balance.earned_usd,
                "claimed": last.balance.claimed_usd,
                "action": last.action.value,
                "reason": last.reason,
                "key_id": last.status.key_id if last.status else None,
                "key_spend": last.status.spend_usd if last.status else 0.0,
                "key_remaining": last.status.remaining_usd if last.status else 0.0,
            }
        return _TEMPLATES.TemplateResponse(
            "index.html",
            {
                "request": request,
                "wallet_label": settings.wallet_label,
                "wallet": settings.orbio_wallet,
                "low_balance": settings.low_balance_usd,
                "topup_threshold": settings.topup_threshold,
                "key_cap": settings.key_cap_usd,
                "current": cur,
            },
        )

    @app.get("/api/state")
    async def state() -> Dict[str, Any]:
        last = bot.last_tick
        if last is None:
            return {"status": "no_tick_yet", "ts": time.time()}
        return {
            "status": "ok",
            "ts": last.ts,
            "balance": {
                "earned_usd": last.balance.earned_usd,
                "claimed_usd": last.balance.claimed_usd,
                "unclaimed_usd": last.balance.unclaimed_usd,
            },
            "action": last.action.value,
            "reason": last.reason,
            "key": (
                {
                    "key_id": last.status.key_id,
                    "spend_usd": last.status.spend_usd,
                    "remaining_usd": last.status.remaining_usd,
                    "headroom_usd": last.status.headroom_usd,
                    "used_fraction": last.status.used_fraction,
                }
                if last.status
                else None
            ),
        }

    @app.get("/api/events")
    async def events(limit: int = 50) -> List[Dict[str, Any]]:
        return await bot.state.recent_events(limit=min(limit, 200))

    @app.get("/api/balances")
    async def balances(limit: int = 100) -> List[Dict[str, Any]]:
        return await bot.state.recent_balances(limit=min(limit, 500))

    @app.post("/api/claim")
    async def claim():
        try:
            async with bot.mcp:
                key = await bot.mcp.claim_key(cap_usd=settings.key_cap_usd)
        except OrbioMCPError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return {"key_id": key.key_id, "headroom_usd": key.headroom_usd}

    @app.post("/api/rotate")
    async def rotate():
        cur = await bot.state.current_key()
        if cur is None:
            raise HTTPException(status_code=400, detail="no current key to rotate")
        try:
            async with bot.mcp:
                new_key = await bot.mcp.rotate_key(cur.key_id)
        except OrbioMCPError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return {
            "old_key_id": cur.key_id,
            "new_key_id": new_key.key_id,
            "headroom_usd": new_key.headroom_usd,
        }

    @app.post("/api/topup")
    async def topup(body: TopUpBody):
        cur = await bot.state.current_key()
        if cur is None:
            raise HTTPException(status_code=400, detail="no current key to top up")
        if body.amount <= 0 or body.amount > settings.key_cap_usd:
            raise HTTPException(
                status_code=400,
                detail=f"amount must be in (0, {settings.key_cap_usd}]",
            )
        try:
            async with bot.mcp:
                new_key = await bot.mcp.top_up_key(cur.key_id, body.amount)
        except OrbioMCPError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return {
            "key_id": new_key.key_id,
            "headroom_usd": new_key.headroom_usd,
            "spend_usd": new_key.spend_usd,
        }

    return app


def run_dashboard(bot: BagBot, settings: Settings) -> None:
    import uvicorn

    app = build_app(bot, settings)
    uvicorn.run(
        app,
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        log_level="info",
    )
