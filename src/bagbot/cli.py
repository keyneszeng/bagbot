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
    """Exercise the 5 live MCP tools and print the results.

    Read-only by default.  With --live it also does a real
    create → revoke cycle (does NOT touch the legacy delete tool).
    """
    from .orbio_mcp import OrbioMCPClient

    s = _settings_or_die()
    live = bool(getattr(args, "live", False))
    async with OrbioMCPClient(s.orbio_mcp_url, s.orbio_mcp_token) as c:
        print("→ orbio_get_balance")
        bal = await c.get_balance()
        _dump("  balance:", bal.raw)

        print("\n→ orbio_get_key_status")
        st = await c.get_key_status()
        _dump("  status:", st.raw)

        if live:
            print("\n→ orbio_create_key (live; any existing key is retired)")
            key = await c.create_key(label="bagbot-probe")
            # The secret is shown exactly once — print only its head.
            _dump("  key (redacted):", {
                "prefix": key.prefix,
                "base_url": key.base_url,
                "replaced": key.replaced,
                "secret_head": (key.secret[:12] + "…") if key.secret else "",
            }, redact=False)

            print("\n→ orbio_revoke_key")
            rev = await c.revoke_key()
            _dump("  revoke:", {"revoked": rev.revoked}, redact=False)
            print("\n(live cycle done — key created then revoked)")
        else:
            print("\n(skip create/revoke — pass --live to exercise them for real)")

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
    async with bot.require_mcp():
        await bot.run_forever()
    return 0


async def cmd_once(args) -> int:
    from .daemon import BagBot
    s = _settings_or_die()
    bot = BagBot(s)
    await bot.state.init()
    async with bot.require_mcp():
        report = await bot.tick()
    print(json.dumps({
        "ts": report.ts,
        "balance_unclaimed_usd": report.balance.unclaimed_usd,
        "balance_accrued_usd": report.balance.accrued_usd,
        "has_key": report.status.has_key if report.status else False,
        "key_prefix": report.status.prefix if report.status else None,
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
        print(f"  {k.key_id[:14]} headroom=${k.headroom_usd:.2f} "
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
    await run_dashboard(bot, s)
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    from .orbio_mcp import OrbioMCPError

    p = argparse.ArgumentParser(prog="bagbot")
    p.add_argument("--log-level", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="Run the daemon (foreground)")
    sub.add_parser("probe", help="Exercise the 5 live MCP tools and print results")
    sub.choices["probe"].add_argument("--live", action="store_true",
                                      help="also run a real create→revoke key cycle")
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
    try:
        return asyncio.run(table[args.cmd](args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except OrbioMCPError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        print(
            "  Hint: check ORBIO_MCP_URL and ORBIO_MCP_TOKEN in your .env.",
            file=sys.stderr,
        )
        return 1
    except SystemExit as e:
        # Don't wrap _settings_or_die()'s intentional exit codes.
        return int(e.code) if e.code is not None else 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        print("  Last 5 traceback lines:", file=sys.stderr)
        tb_lines = traceback.format_exc().splitlines()
        for line in tb_lines[-5:]:
            print(f"    {line}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
