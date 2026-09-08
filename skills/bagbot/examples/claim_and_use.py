"""Example: create the Orbio gateway key and use it.

Gateway model (2026-09-08): the key holds no credit — it spends the
account balance request-by-request at an OpenAI-compatible base_url.
The secret is shown exactly once by orbio_create_key.

Run (from repo root or anywhere):
    export ORBIO_WALLET=0xYourWallet
    export ORBIO_MCP_TOKEN=your-token
    PYTHONPATH=skills/bagbot/scripts python3 examples/claim_and_use.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bagbot_orbio  # noqa: E402


async def main() -> None:
    # (the gateway key is free — there is no cap to choose)
    async with bagbot_orbio.OrbioClient.from_env() as c:
        bal = await c.get_balance()
        print(f"unclaimed: ${bal.unclaimed_usd:.2f}")

        if bal.unclaimed_usd < 5.0:
            print("Not enough unclaimed credit yet. Hold $ORBIO and wait an hour.")
            return

        status = await c.get_key_status()
        if status.has_key:
            print(f"key already exists ({status.prefix}); rotating (secret re-issued)")
        key = await c.create_key(label="skill-example")
        print(f"key prefix : {key.prefix}  (replaced: {key.replaced})")
        print(f"base_url   : {key.base_url}")
        # SECURITY: never log key.secret to CI / chats. Use it in your app.
        # e.g. os.environ["OPENAI_API_KEY"] = key.secret
        #      os.environ["OPENAI_BASE_URL"] = key.base_url
        print("now point your LLM client at that base_url with the secret "
              "(kept in memory, not printed here).")


if __name__ == "__main__":
    asyncio.run(main())
