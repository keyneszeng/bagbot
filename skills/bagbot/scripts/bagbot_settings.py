"""bagbot skill — settings / env loader facade.

    import bagbot_bootstrap            # noqa: F401
    from bagbot_settings import Settings, load_settings
"""

from __future__ import annotations

import bagbot_bootstrap  # noqa: F401

from bagbot.config import (  # noqa: F401
    DashboardCfg,
    NotifierCfg,
    Settings,
    get_settings as load_settings,
)

__all__ = ["Settings", "NotifierCfg", "DashboardCfg", "load_settings"]
