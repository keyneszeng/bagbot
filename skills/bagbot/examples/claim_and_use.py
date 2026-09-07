"""Example: claim an OpenRouter key from your $ORBIO balance and use it.

Run (from repo root or anywhere):
    export ORBIO_WALLET=0xYourWallet
    export ORBIO_MCP_TOKEN=your-token
    PYTHONPATH=skills/bagbot/scripts python3 examples/claim_and_use.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bagbot_orbio  # noqa: E402


async def main() -> None:
    cap = float(os.environ.get("CLAIM_CAP_USD", "10.0"))
    async with bagbot_orbio.OrbioClient.from_env() as c:
        bal = await c.get_balance()
        print(f"unclaimed: ${bal.unclaimed_usd:.2f}")

        if bal.unclaimed_usd < 5.0:
            print("Not enough unclaimed credit yet. Hold $ORBIO and wait an hour.")
            return

        key = await c.claim_key(cap_usd=cap)
        print(f"claimed key: {key.key_id}")
        print(f"headroom   : ${key.headroom_usd:.2f}")
        # SECURITY: never log key.secret to CI / chats. Use it in your app.
        # e.g. os.environ["OPENROUTER_API_KEY"] = key.secret
        print("now point your LLM client at https://openrouter.ai/api/v1 "
              "with that secret (kept in memory, not printed here).")


if __name__ == "__main__":
    asyncio.run(main())
