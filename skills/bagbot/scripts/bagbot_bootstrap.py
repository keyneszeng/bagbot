"""Path bootstrap for the bagbot skill.

Makes the *real* `bagbot` package importable when this skill is copied
anywhere (an agent's skill dir, a fresh clone, a tarball) without a pip
install.  Two strategies:

1. If the main repo's `src/` is present relative to this file, add it.
2. Otherwise, if `bagbot` is pip-installed, it just imports normally.

Usage from any agent script:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # optional
    import bagbot_bootstrap  # noqa: F401  (ensures src/ is on sys.path)
    from bagbot.orbio_mcp import OrbioClient
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Look for the real repo: skills/bagbot/scripts/ -> repo root is 3 up
_candidates = [
    _HERE.parents[2] / "src",                 # <repo>/skills/bagbot/scripts -> <repo>/src
    _HERE.parents[3] / "src",                 # one level deeper fallback
    Path(os.environ.get("BAGBOT_SRC", "")) if os.environ.get("BAGBOT_SRC") else None,
]

added: list[str] = []
for c in _candidates:
    if c is None:
        continue
    if (c / "bagbot" / "__init__.py").exists():
        _src = str(c.resolve())
        if _src not in sys.path:
            sys.path.insert(0, _src)
            added.append(_src)
        break

__all__ = ["added", "src_paths"]


def src_paths() -> list[str]:
    return added
