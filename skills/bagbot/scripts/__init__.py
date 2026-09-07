"""Make `import bagbot_orbio` etc. work when the scripts dir is on PYTHONPATH.

Public surface of the skill scripts:
- `OrbioClient` (6 MCP tools) from bagbot_orbio
- `decide` / `PolicyConfig` / `Snapshot` / `Action` from bagbot_policy
- `Settings` / `load_settings` from bagbot_settings
"""

from __future__ import annotations

import bagbot_bootstrap  # noqa: F401  (put real src/ on sys.path)

from bagbot_orbio import (  # noqa: F401
    Balance,
    Key,
    KeyStatus,
    OrbioClient,
    OrbioMCPError,
)
from bagbot_policy import (  # noqa: F401
    Action,
    PolicyConfig,
    Snapshot,
    decide,
)
from bagbot_settings import (  # noqa: F401
    DashboardCfg,
    NotifierCfg,
    Settings,
    load_settings,
)

__all__ = [
    "OrbioClient",
    "OrbioMCPError",
    "Balance",
    "Key",
    "KeyStatus",
    "Action",
    "PolicyConfig",
    "Snapshot",
    "decide",
    "Settings",
    "NotifierCfg",
    "DashboardCfg",
    "load_settings",
]
