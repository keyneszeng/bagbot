"""Tests for CLI top-level error handling."""

import os
import subprocess
import sys


def test_no_token_exits_with_code_2():
    """probe with no token should print a clear error and exit 2."""
    env = {k: v for k, v in os.environ.items() if k not in ("ORBIO_MCP_TOKEN", "ORBIO_WALLET")}
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "probe"],
        capture_output=True, text=True, env=env, cwd="/Users/mac/Desktop/deepseek/bagbot",
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    assert "ORBIO_MCP_TOKEN" in result.stderr


def test_no_wallet_exits_with_code_2():
    """probe with token but no wallet should also exit 2."""
    env = {k: v for k, v in os.environ.items() if k not in ("ORBIO_WALLET",)}
    env["ORBIO_MCP_TOKEN"] = "fake_token_for_test"
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "probe"],
        capture_output=True, text=True, env=env, cwd="/Users/mac/Desktop/deepseek/bagbot",
    )
    assert result.returncode == 2
    assert "ORBIO_WALLET" in result.stderr


def test_help_works():
    """--help should print usage and exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "bagbot.cli", "--help"],
        capture_output=True, text=True, cwd="/Users/mac/Desktop/deepseek/bagbot",
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "probe" in result.stdout
    assert "run" in result.stdout
