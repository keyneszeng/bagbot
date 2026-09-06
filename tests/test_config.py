"""Config loader tests — verify defaults + env override + validation."""

import os
from pathlib import Path

import pytest

from bagbot import config as cfg_module


def test_settings_default_when_no_env(tmp_path, monkeypatch):
    """With no .env and no env vars, Settings should return defaults."""
    # Make sure no .env is loaded
    monkeypatch.chdir(tmp_path)
    # Reload module to re-read CWD-relative .env
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    assert s.poll_interval_sec == 300
    assert s.low_balance_usd == 5.0
    assert s.topup_threshold == 0.8
    assert s.rotate_max_age_hours == 168
    assert s.key_cap_usd == 200.0
    assert s.dashboard.host == "127.0.0.1"
    assert s.dashboard.port == 8765


def test_env_overrides_take_effect(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POLL_INTERVAL_SEC", "60")
    monkeypatch.setenv("LOW_BALANCE_USD", "12.5")
    monkeypatch.setenv("LANGUAGE", "en")
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    assert s.poll_interval_sec == 60
    assert s.low_balance_usd == 12.5
    assert s.language == "en"


def test_invalid_int_falls_back_to_default(monkeypatch, tmp_path):
    """Bad values should not crash."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POLL_INTERVAL_SEC", "not-a-number")
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    assert s.poll_interval_sec == 300  # default


def test_invalid_float_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KEY_CAP_USD", "garbage")
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    assert s.key_cap_usd == 200.0  # default


def test_notifier_enabled_when_any_channel_set(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FEISHU_ENABLED", "true")
    cfg_module.reload_settings()
    s = cfg_module.get_settings()
    assert s.notifier.enabled is True
    assert s.notifier.feishu_webhook_url == ""  # not set, but enabled flag on


def test_bool_env_parsing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for v in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("FEISHU_ENABLED", v)
        cfg_module.reload_settings()
        assert cfg_module.get_settings().notifier.enabled is True, f"failed for {v!r}"
    for v in ("0", "false", "no", ""):
        monkeypatch.setenv("FEISHU_ENABLED", v)
        cfg_module.reload_settings()
        assert cfg_module.get_settings().notifier.enabled is False, f"failed for {v!r}"
