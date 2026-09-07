"""bagbot skill — pure-function decision policy.

Zero-dependency facade over the real policy engine so an agent can decide
what to do (CLAIM / TOPUP / ROTATE / DELETE / ALERT / NOTHING) without
touching any network or state.

    import bagbot_bootstrap            # noqa: F401
    from bagbot_policy import decide, PolicyConfig, Snapshot
"""

from __future__ import annotations

import bagbot_bootstrap  # noqa: F401

from bagbot.policy import (  # noqa: F401
    Action,
    PolicyConfig,
    Snapshot,
    decide,
)

__all__ = ["Action", "PolicyConfig", "Snapshot", "decide"]
