"""bagbot skill — re-export of the 5-tool Orbio gateway MCP client.

Importable by any agent with zero install when placed alongside the repo,
or after `pip install bagbot`.  Thin, documented facade.

Live API (verified 2026-09-08): get_balance / get_key_status /
create_key / revoke_key / delete_key.  Gateway model — the key holds no
credit itself; it spends the account balance request-by-request.

Typical usage:

    import asyncio
    import bagbot_bootstrap            # noqa: F401
    from bagbot_orbio import OrbioClient

    async def main():
        async with OrbioClient.from_env() as c:
            balance = await c.get_balance()      # balance IS the quota
            status = await c.get_key_status()    # per-account, no args
            if not status.has_key:
                key = await c.create_key(label="my-box")   # secret: once!
                # → key.secret shown exactly once; store it now.

    asyncio.run(main())
"""

from __future__ import annotations

import bagbot_bootstrap  # noqa: F401  (ensures real src/ is importable)

# The real client class is `OrbioMCPClient`; we expose the friendlier alias.
from bagbot.orbio_mcp import (  # noqa: F401
    Balance,
    DeleteResult,
    Key,
    KeyStatus,
    OrbioMCPClient as OrbioClient,
    OrbioMCPError,
    RevokeResult,
)

__all__ = [
    "OrbioClient",
    "OrbioMCPError",
    "Balance",
    "Key",
    "KeyStatus",
    "RevokeResult",
    "DeleteResult",
]
