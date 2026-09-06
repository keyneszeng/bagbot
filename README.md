# BagBot

> **The first open-source, self-funding, self-healing AI daemon — for agents on Orbio.**
>
> Orbio 让你用持币就能赚 LLM 额度,但还是要有人 claim key、watch 余额、rotate 旧 key。
> BagBot 是第一个把这些脏活累活**完全自动化**、并支持**中文通知**的 daemon。
> 你的 Agent 不再需要你充钱, 它会自己管自己。
>
> Orbio lets you earn LLM credits just by holding tokens — but somebody still has to claim keys, watch balances, and rotate old ones. **BagBot is the first daemon that fully automates all that messy work, with Chinese-language notifications built in.** Your agent no longer needs you to top it up — it manages itself.

[![Orbio Build Week](https://img.shields.io/badge/Orbio-Build%20Week-7B61FF)](https://orbio.so/build)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

## 🪐 What is BagBot?

BagBot is a 7×24 unattended Python daemon that:

1. **Monitors** your `$ORBIO` balance via the [Orbio MCP](https://orbio.so/mcp) `orbio_get_balance` (every 5 min)
2. **Auto-claims** a fresh OpenRouter key when the current one is running low (`orbio_claim_key`)
3. **Watches** your key's spend in real time via `orbio_get_key_status`
4. **Auto-tops-up** before the key dies (`orbio_top_up_key`)
5. **Auto-rotates** the key on anomaly detection (`orbio_rotate_key`)
6. **Auto-kills** the key on catastrophic events (`orbio_delete_key`)
7. **Reports** everything to WeChat / Feishu / Email / Webhook in **Chinese** + a local dashboard
8. **Runs as a service** via `launchd` (macOS) / `systemd` (Linux)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│                 BagBot                       │
├──────────────────────────────────────────────┤
│  ┌────────────┐    ┌──────────────────────┐  │
│  │   Daemon   │───▶│  Orbio MCP Client    │  │
│  │  (asyncio) │    │  (6 tools wrapper)   │  │
│  └─────┬──────┘    └──────────────────────┘  │
│        │                                      │
│        ├────▶ State Store (SQLite)            │
│        ├────▶ Notifiers (中文优先)           │
│        │       ├── WeChat Work / 公众号       │
│        │       ├── Feishu / Lark webhook      │
│        │       ├── Email (SMTP)              │
│        │       └── Generic Webhook           │
│        └────▶ FastAPI Dashboard (Chinese)    │
└──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

```bash
# 1. Install
git clone https://github.com/keyneszeng/bagbot.git
cd bagbot
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: fill in ORBIO_WALLET, NOTIFIER_WEBHOOK, etc.

# 3. First-time: test all 6 MCP tools
python -m bagbot.cli probe

# 4. Start daemon (foreground)
python -m bagbot.cli run

# 5. Or install as a service (macOS launchd)
bash scripts/install_launchd.sh
```

---

## 🇨🇳 中文用户教程

完整中文实操指南: [`docs/guide.zh-CN.md`](docs/guide.zh-CN.md)

---

## 📦 What you get out of the box

| File | What it does |
|---|---|
| `src/bagbot/orbio_mcp.py` | Python async client wrapping all 6 Orbio MCP tools |
| `src/bagbot/daemon.py` | Core 7×24 event loop (monitor → decide → act → report) |
| `src/bagbot/policy.py` | Pluggable decision rules (low-balance, anomaly, rotation age) |
| `src/bagbot/state.py` | SQLite state store (balances, keys, events, history) |
| `notifiers/*.py` | 4 notifier adapters, all with Chinese templates |
| `dashboard/app.py` | FastAPI web UI, Chinese-first |
| `scripts/install_launchd.sh` | One-command macOS service install |
| `scripts/install_systemd.sh` | One-command Linux service install |

---

## 🎯 Built for Orbio Build Week

This project was built in 7 days for [Orbio Build Week](https://orbio.so/build)
(7-day competition, 8M `$ORBIO` prize, 10 winners).

**Builder**: [@keyneszeng](https://github.com/keyneszeng) · X: [@keyneszeng](https://x.com/keyneszeng)
**Live project**: [github.com/keyneszeng/bagbot](https://github.com/keyneszeng/bagbot)

---

## 📜 License

MIT — take anything. Same as [orbio-starter](https://github.com/aster2709/orbio-starter).
