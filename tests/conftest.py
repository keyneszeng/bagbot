"""Shared pytest fixtures and configuration for the BagBot test suite.

This file lives at tests/conftest.py so pytest picks it up automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the src/ layout importable for pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear the module-level `_cached` Settings before each test.

    Why: tests modify env vars (ORBIO_MCP_TOKEN, DASHBOARD_TOKEN, etc.)
    via monkeypatch.  The cached `get_settings()` would otherwise return
    a Settings object built from PREVIOUS test's env, causing flaky
    failures under pytest-xdist parallelism.

    Runs for every test automatically (autouse=True).
    """
    from bagbot import config as cfg_module
    cfg_module._cached = None
    yield
    cfg_module._cached = None
