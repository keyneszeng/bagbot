"""bagbot skill CLI — `python bagbot_cli.py probe|status|decide ...`.

Works from anywhere inside (or beside) the repo without install, and
respects `BAGBOT_SRC` env var if the repo lives elsewhere.

`decide` and `help` have **zero third-party dependencies** (pure policy).
`probe` / `status` lazy-load the network + sqlite modules only when run.

Examples:
    python bagbot_cli.py probe              # exercise 6 MCP tools (redacted)
    python bagbot_cli.py status             # local SQLite snapshot
    python bagbot_cli.py decide 10.0        # what should I do with $10?
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import bagbot_bootstrap  # noqa: E402,F401
import bagbot_policy  # noqa: E402


def _redact(text: str) -> str:
    import re
    return re.sub(r"(sk-or-v1-[A-Za-z0-9._-]{10,})", r"sk-or-v1-***REDACTED***", text)


async def _probe() -> int:
    import bagbot_orbio
    import bagbot_settings

    s = bagbot_settings.load_settings()
    if not s.orbio_mcp_token or not s.orbio_wallet:
        print("Set ORBIO_MCP_TOKEN and ORBIO_WALLET (env or .env) first.", file=sys.stderr)
        return 2
    print(f"Orbio MCP : {s.orbio_mcp_url}")
    print(f"Wallet    : {s.orbio_wallet[:10]}…{s.orbio_wallet[-4:] if len(s.orbio_wallet) > 14 else ''}")
    print()
    async with bagbot_orbio.OrbioClient.from_env() as c:
        bal = await c.get_balance()
        print("→ orbio_get_balance")
        print(f"    unclaimed: ${bal.unclaimed_usd:.2f}  claimed: ${bal.claimed_usd:.2f}  earned: ${bal.earned_usd:.2f}")
        print()
        print("→ orbio_claim_key(cap=5) [probe mints + destroys a tiny key]")
        key = await c.claim_key(cap_usd=5.0)
        print(f"    key_id: {key.key_id}  headroom: ${key.headroom_usd:.2f}")
        st = await c.get_key_status(key.key_id)
        print(f"    status: spend ${st.spend_usd:.2f}  remaining ${st.remaining_usd:.2f}")
        await c.delete_key(key.key_id)
        print("    deleted (probe key cleaned up)")
    print()
    print("✓ probe OK")
    return 0


async def _status() -> int:
    import bagbot_settings

    from bagbot.state import StateStore

    s = bagbot_settings.load_settings()
    store = StateStore(s.state_db_path)
    await store.init()
    keys = await store.recent_keys(limit=3)
    evs = await store.recent_events(limit=8)
    print(f"state db : {s.state_db_path}")
    print(f"keys     : {len(keys)} total (recent {len(keys)})")
    for k in keys:
        print(f"    {k.key_id[:16]}…  retired={'yes' if k.retired_at else 'no'}")
    print("events   :")
    for e in evs:
        print(f"    [{e['level']}] {e['kind']} — {e['message'][:80]}")
    return 0


async def _decide(unclaimed_str: str) -> int:
    try:
        unclaimed = float(unclaimed_str)
    except ValueError:
        print("usage: bagbot_cli.py decide <unclaimed_usd>", file=sys.stderr)
        return 2
    snap = bagbot_policy.Snapshot(
        has_key=False, key_id=None, key_age_hours=0.0,
        spend_rate_usd_per_hour=0.0, key_used_fraction=0.0,
        key_remaining_usd=0.0, unclaimed_usd=unclaimed,
        earned_usd=unclaimed, claimed_usd=0.0,
    )
    action, reason = bagbot_policy.decide(snap, bagbot_policy.PolicyConfig())
    print(f"action: {action.value}")
    print(f"reason: {reason}")
    return 0


async def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "probe":
        return await _probe()
    if cmd == "status":
        return await _status()
    if cmd == "decide" and len(argv) >= 2:
        return await _decide(argv[1])
    print(f"unknown command: {cmd!r}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
