"""BagBot CLI — `python -m bagbot.cli <subcommand>`.

Subcommands:
  run         — start the daemon (foreground)
  probe       — exercise all 6 MCP tools, print results, exit
  status      — print last tick state from the local DB
  dashboard   — start the dashboard web UI
  once        — run exactly one daemon tick and exit (smoke test)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Optional

from .config import get_settings
from .logging_setup import setup_logging

log = logging.getLogger("bagbot.cli")


# Fields that should never end up on stdout / in a JSON dump.
# Match is case-insensitive on the key name, applied recursively to dicts
# and lists.
_REDACT_KEYS = {
    "secret", "sk_or_v1", "sk-or-v1", "sk_live", "sk_test",
    "authorization", "api_key", "apikey", "token", "password",
    "private_key", "seed", "mnemonic",
}


def _redact(obj):
    """Return a deep-copied version of `obj` with sensitive fields replaced
    by '***REDACTED***'.  Recurses into dicts and lists."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _REDACT_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _dump(label: str, obj, *, redact: bool = True) -> None:
    """Pretty-print `obj` as JSON.  When `redact` is True (default), sensitive
    fields are replaced with '***REDACTED***' before printing."""
    print(label)
    if redact:
        obj = _redact(obj)
    print(json.dumps(obj, indent=2, default=str))


def _settings_or_die():
    s = get_settings()
    if not s.orbio_mcp_token:
        print(
            "ORBIO_MCP_TOKEN is empty. Set it in .env or your environment.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not s.orbio_wallet:
        print(
            "ORBIO_WALLET is empty. Set it in .env or your environment.",
            file=sys.stderr,
        )
        sys.exit(2)
    return s


async def cmd_probe(args) -> int:
    """Exercise all 6 MCP tools and print the results."""
    from .orbio_mcp import OrbioMCPClient

    s = _settings_or_die()
    async with OrbioMCPClient(s.orbio_mcp_url, s.orbio_mcp_token) as c:
        print("→ orbio_get_balance")
        bal = await c.get_balance()
        _dump("  balance:", bal.raw)

        print("\n→ orbio_claim_key (cap=10 USD, dry-style probe)")
        key = await c.claim_key(cap_usd=10.0)
        # Print only non-secret fields of the issued key
        _dump("  key (redacted):", {
            "key_id": key.key_id,
            "headroom_usd": key.headroom_usd,
        }, redact=False)

        print("\n→ orbio_get_key_status")
        st = await c.get_key_status(key.key_id)
        _dump("  status:", st.raw)

        print("\n→ orbio_top_up_key (+5)")
        top = await c.top_up_key(key.key_id, 5.0)
        _dump("  top (redacted):", {
            "key_id": top.key_id,
            "headroom_usd": top.headroom_usd,
        }, redact=False)

        print("\n→ orbio_rotate_key")
        rot = await c.rotate_key(key.key_id)
        _dump("  rotated (redacted):", {
            "key_id": rot.key_id,
            "headroom_usd": rot.headroom_usd,
        }, redact=False)

        print("\n→ orbio_delete_key")
        await c.delete_key(key.key_id)
        print("(deleted)")

    return 0


async def cmd_run(args) -> int:
    from .daemon import BagBot
    s = _settings_or_die()
    bot = BagBot(s)
    # signal handlers
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(
                getattr(__import__("signal"), sig), bot.request_stop
            )
        except (NotImplementedError, RuntimeError):
            pass
    async with bot.mcp:
        await bot.run_forever()
    return 0


async def cmd_once(args) -> int:
    from .daemon import BagBot
    s = _settings_or_die()
    bot = BagBot(s)
    await bot.state.init()
    async with bot.mcp:
        report = await bot.tick()
    print(json.dumps({
        "ts": report.ts,
        "balance_unclaimed_usd": report.balance.unclaimed_usd,
        "key_id": report.status.key_id if report.status else None,
        "action": report.action.value,
        "reason": report.reason,
    }, indent=2, default=str))
    return 0


async def cmd_status(args) -> int:
    from .state import StateStore
    s = get_settings()
    store = StateStore(s.state_db_path)
    await store.init()
    keys = await store.recent_keys(limit=5)
    bal = await store.recent_balances(limit=5)
    events = await store.recent_events(limit=10)
    print("== Recent keys ==")
    for k in keys:
        print(f"  {k.key_id[:10]}… headroom=${k.headroom_usd:.2f} "
              f"spend=${k.spend_usd:.2f} retired={k.retired_at}")
    print("\n== Recent balance snapshots ==")
    for b in bal:
        print(f"  ts={b['ts']:.0f} earned=${b['earned_usd']:.2f} "
              f"claimed=${b['claimed_usd']:.2f} unclaimed=${b['unclaimed_usd']:.2f}")
    print("\n== Recent events ==")
    for e in events:
        print(f"  [{e['level']}] {e['kind']}: {e['message']}")
    return 0


async def cmd_dashboard(args) -> int:
    from .daemon import BagBot
    from .dashboard import run_dashboard

    s = get_settings()
    bot = BagBot(s)
    await bot.state.init()
    run_dashboard(bot, s)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="bagbot")
    p.add_argument("--log-level", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="Run the daemon (foreground)")
    sub.add_parser("probe", help="Exercise all 6 MCP tools once and exit")
    sub.add_parser("once", help="Run exactly one daemon tick and exit")
    sub.add_parser("status", help="Print recent state from local DB")
    sub.add_parser("dashboard", help="Start the dashboard web UI")

    args = p.parse_args(argv)
    s = get_settings()
    setup_logging(
        s.log_file,
        args.log_level or s.log_level,
    )

    table = {
        "run": cmd_run,
        "probe": cmd_probe,
        "once": cmd_once,
        "status": cmd_status,
        "dashboard": cmd_dashboard,
    }
    return asyncio.run(table[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
