"""BagBot configuration loader.

Reads .env (or environment) and exposes a typed Settings object.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Default .env location: project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    return val if val is not None and val != "" else default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = _env(key, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


class NotifierCfg(BaseModel):
    enabled: bool = False
    # Generic webhook
    webhook_url: str = ""
    webhook_secret: str = ""
    # Feishu / Lark
    feishu_webhook_url: str = ""
    feishu_secret: str = ""
    # WeChat Work
    wechat_corp_id: str = ""
    wechat_agent_id: str = ""
    wechat_secret: str = ""
    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""


class DashboardCfg(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    # Optional shared secret for mutating endpoints (claim/rotate/topup).
    # If empty, mutation endpoints are disabled (read-only dashboard).
    # Set DASHBOARD_TOKEN in .env for production / non-localhost use.
    token: str = ""


class Settings(BaseModel):
    # Wallet / identity
    orbio_wallet: str = Field(default="", alias="ORBIO_WALLET")
    wallet_label: str = Field(default="My Wallet", alias="WALLET_LABEL")

    # Orbio MCP
    orbio_mcp_url: str = Field(
        default="https://www.orbio.so/api/mcp", alias="ORBIO_MCP_URL"
    )
    orbio_mcp_token: str = Field(default="", alias="ORBIO_MCP_TOKEN")

    # Policy
    poll_interval_sec: int = Field(default=300, alias="POLL_INTERVAL_SEC")
    low_balance_usd: float = Field(default=5.0, alias="LOW_BALANCE_USD")
    rotate_max_age_hours: int = Field(default=168, alias="ROTATE_MAX_AGE_HOURS")
    rotate_burst_usd_per_hour: float = Field(
        default=20.0, alias="ROTATE_BURST_USD_PER_HOUR"
    )

    # State
    state_db_path: str = Field(default="./data/bagbot.sqlite", alias="STATE_DB_PATH")
    log_file: str = Field(default="./data/bagbot.log", alias="LOG_FILE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Dashboard
    dashboard: DashboardCfg = DashboardCfg()

    # Notifiers
    notifier: NotifierCfg = NotifierCfg()

    # Locale
    language: str = Field(default="zh-CN", alias="LANGUAGE")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            ORBIO_WALLET=_env("ORBIO_WALLET"),
            WALLET_LABEL=_env("WALLET_LABEL", "My Wallet"),
            ORBIO_MCP_URL=_env("ORBIO_MCP_URL", "https://www.orbio.so/api/mcp"),
            ORBIO_MCP_TOKEN=_env("ORBIO_MCP_TOKEN"),
            POLL_INTERVAL_SEC=_env_int("POLL_INTERVAL_SEC", 300),
            LOW_BALANCE_USD=_env_float("LOW_BALANCE_USD", 5.0),
            ROTATE_MAX_AGE_HOURS=_env_int("ROTATE_MAX_AGE_HOURS", 168),
            ROTATE_BURST_USD_PER_HOUR=_env_float("ROTATE_BURST_USD_PER_HOUR", 20.0),
            STATE_DB_PATH=_env("STATE_DB_PATH", "./data/bagbot.sqlite"),
            LOG_FILE=_env("LOG_FILE", "./data/bagbot.log"),
            LOG_LEVEL=_env("LOG_LEVEL", "INFO"),
            dashboard=DashboardCfg(
                enabled=_env_bool("DASHBOARD_ENABLED", True),
                host=_env("DASHBOARD_HOST", "127.0.0.1"),
                port=_env_int("DASHBOARD_PORT", 8765),
                token=_env("DASHBOARD_TOKEN", ""),
            ),
            notifier=NotifierCfg(
                enabled=_env_bool("WEBHOOK_ENABLED", False)
                or _env_bool("FEISHU_ENABLED", False)
                or _env_bool("WECHAT_ENABLED", False)
                or _env_bool("EMAIL_ENABLED", False),
                webhook_url=_env("WEBHOOK_URL"),
                feishu_webhook_url=_env("FEISHU_WEBHOOK_URL"),
                feishu_secret=_env("FEISHU_SECRET"),
                wechat_corp_id=_env("WECHAT_CORP_ID"),
                wechat_agent_id=_env("WECHAT_AGENT_ID"),
                wechat_secret=_env("WECHAT_SECRET"),
                smtp_host=_env("SMTP_HOST"),
                smtp_port=_env_int("SMTP_PORT", 587),
                smtp_username=_env("SMTP_USERNAME"),
                smtp_password=_env("SMTP_PASSWORD"),
                email_from=_env("EMAIL_FROM"),
                email_to=_env("EMAIL_TO"),
            ),
            LANGUAGE=_env("LANGUAGE", "zh-CN"),
            TIMEZONE=_env("TIMEZONE", "Asia/Shanghai"),
        )


_cached: Settings | None = None


def get_settings() -> Settings:
    """Cached settings accessor."""
    global _cached
    if _cached is None:
        _cached = Settings.from_env()
    return _cached


def reload_settings() -> Settings:
    global _cached
    _cached = Settings.from_env()
    return _cached
