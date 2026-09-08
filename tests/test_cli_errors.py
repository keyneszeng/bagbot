"""Tests for CLI top-level error handling."""

import os
import subprocess
import sys
from pathlib import Path

# Project root (portable — no hard-coded developer machine path).
_ROOT = Path(__file__).resolve().parents[1]


def test_no_token_exits_with_code_2():
    """probe with no token should print a clear error and exit 2."""
    # NOTE: the repo .env (with a real token) is loaded by dotenv at import
    # time — simply *removing* the env var is not enough.  Set them to ""
    # explicitly so the CLI sees an empty token, not the .env value.
    env = dict(os.environ)
    env["ORBIO_MCP_TOKEN"] = ""
    env.pop("ORBIO_WALLET", None)
    env["PYTHONPATH"] = str(_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "probe"],
        capture_output=True, text=True, env=env, cwd=str(_ROOT),
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}; stderr={result.stderr!r}"
    assert "ORBIO_MCP_TOKEN" in result.stderr


def test_no_wallet_exits_with_code_2():
    """probe with token but no wallet should also exit 2."""
    # Explicit empty wallet (the repo .env has a real one that dotenv
    # would otherwise back-fill into Settings).
    env = dict(os.environ)
    env["ORBIO_MCP_TOKEN"] = "fake_token_for_test"
    env["ORBIO_WALLET"] = ""
    env["PYTHONPATH"] = str(_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "probe"],
        capture_output=True, text=True, env=env, cwd=str(_ROOT),
    )
    assert result.returncode == 2
    assert "ORBIO_WALLET" in result.stderr


def test_help_works():
    """--help should print usage and exit 0."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "--help"],
        capture_output=True, text=True, env=env, cwd=str(_ROOT),
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "probe" in result.stdout
    assert "run" in result.stdout
