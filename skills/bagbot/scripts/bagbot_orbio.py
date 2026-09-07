"""bagbot skill — re-export of the 6-tool Orbio MCP client.

Importable by any agent with zero install when placed alongside the repo,
or after `pip install bagbot`.  Thin, documented facade.

Typical usage:

    import asyncio
    import bagbot_bootstrap            # noqa: F401
    from bagbot_orbio import OrbioClient

    async def main():
        async with OrbioClient.from_env() as c:
            balance = await c.get_balance()
            key = await c.claim_key(cap_usd=10.0)
            await c.rotate_key(key.key_id)

    asyncio.run(main())
"""

from __future__ import annotations

import bagbot_bootstrap  # noqa: F401  (ensures real src/ is importable)

# The real client class is `OrbioMCPClient`; we expose the friendlier alias.
from bagbot.orbio_mcp import (  # noqa: F401
    Balance,
    Key,
    KeyStatus,
    OrbioMCPClient as OrbioClient,
    OrbioMCPError,
)

__all__ = [
    "OrbioClient",
    "OrbioMCPError",
    "Balance",
    "Key",
    "KeyStatus",
]
