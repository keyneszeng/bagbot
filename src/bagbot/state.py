"""Persistent state store backed by SQLite (via aiosqlite).

Tracks the current key, historical keys, balance snapshots, and events.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger("bagbot.state")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    key_id          TEXT PRIMARY KEY,
    secret          TEXT NOT NULL,
    headroom_usd    REAL NOT NULL,
    spend_usd       REAL NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    retired_at      REAL,
    retire_reason   TEXT
);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    earned_usd      REAL NOT NULL,
    claimed_usd     REAL NOT NULL,
    unclaimed_usd   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    level           TEXT NOT NULL,
    kind            TEXT NOT NULL,
    message         TEXT NOT NULL,
    payload_json    TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_balance_ts ON balance_snapshots(ts);
"""


@dataclass
class KeyRecord:
    key_id: str
    secret: str
    headroom_usd: float
    spend_usd: float
    created_at: float
    retired_at: float | None = None
    retire_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        log.info("state store initialised at %s", self.db_path)

    # ── Keys ────────────────────────────────────────────────────────

    async def save_key(self, rec: KeyRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO keys
                   (key_id, secret, headroom_usd, spend_usd,
                    created_at, retired_at, retire_reason)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    rec.key_id, rec.secret, rec.headroom_usd, rec.spend_usd,
                    rec.created_at, rec.retired_at, rec.retire_reason,
                ),
            )
            await db.commit()

    async def retire_key(self, key_id: str, reason: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE keys SET retired_at=?, retire_reason=?
                   WHERE key_id=? AND retired_at IS NULL""",
                (time.time(), reason, key_id),
            )
            await db.commit()

    async def retire_all_active(self, reason: str) -> int:
        """Retire every currently-active key row.  Returns rows affected.

        Used when the server says a new key replaced an old one and we
        don't know the old record's id (e.g. manual create via dashboard).
        """
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """UPDATE keys SET retired_at=?, retire_reason=?
                   WHERE retired_at IS NULL""",
                (time.time(), reason),
            )
            await db.commit()
            return cur.rowcount or 0

    async def current_key(self) -> KeyRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM keys
                   WHERE retired_at IS NULL
                   ORDER BY created_at DESC
                   LIMIT 1"""
            )
            row = await cur.fetchone()
            if not row:
                return None
            return KeyRecord(**dict(row))

    async def recent_keys(self, limit: int = 20) -> list[KeyRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM keys ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [KeyRecord(**dict(r)) async for r in cur]

    # ── Balance snapshots ───────────────────────────────────────────

    async def record_balance(
        self, earned_usd: float, claimed_usd: float, unclaimed_usd: float
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO balance_snapshots
                   (ts, earned_usd, claimed_usd, unclaimed_usd)
                   VALUES (?,?,?,?)""",
                (time.time(), earned_usd, claimed_usd, unclaimed_usd),
            )
            await db.commit()

    async def recent_balances(self, limit: int = 200) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM balance_snapshots
                   ORDER BY ts DESC LIMIT ?""", (limit,)
            )
            return [dict(r) async for r in cur]

    # ── Events / log ────────────────────────────────────────────────

    async def log_event(
        self, level: str, kind: str, message: str, payload: dict | None = None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO events (ts, level, kind, message, payload_json)
                   VALUES (?,?,?,?,?)""",
                (time.time(), level, kind, message,
                 json.dumps(payload) if payload else None),
            )
            await db.commit()

    async def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            )
            out: list[dict[str, Any]] = []
            async for r in cur:
                d = dict(r)
                if d.get("payload_json"):
                    try:
                        d["payload"] = json.loads(d.pop("payload_json"))
                    except json.JSONDecodeError:
                        pass
                out.append(d)
            return out
