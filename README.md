# BagBot

> **The first open-source, self-funding, self-healing AI daemon — for agents on Orbio.**
>
> Orbio 让你用持币就能赚 LLM 额度,但还是要有人 claim key、watch 余额、rotate 旧 key。
> BagBot 是第一个把这些脏活累活**完全自动化**、并支持**中文通知**的 daemon。
> 你的 Agent 不再需要你充钱, 它会自己管自己。
>
> Orbio lets you earn LLM credits just by holding tokens — but somebody still has to claim keys, watch balances, and rotate old ones. **BagBot is the first daemon that fully automates all that messy work, with Chinese-language notifications built in.** Your agent no longer needs you to top it up — it manages itself.

[![Orbio Build Week](https://img.shields.io/badge/Orbio-Build%20Week-7B61FF)](https://orbio.so/build)
[![CI](https://github.com/keyneszeng/bagbot/workflows/CI/badge.svg)](https://github.com/keyneszeng/bagbot/actions)
[![Mutation Testing](https://github.com/keyneszeng/bagbot/workflows/Mutation%20Testing%20(nightly)/badge.svg)](https://github.com/keyneszeng/bagbot/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-120%20passing-brightgreen.svg)](tests/)
[![Mutation score: 92.9%](https://img.shields.io/badge/mutation%20score%20(policy)-92.9%25-brightgreen.svg)](scripts/mutation_test.py)

---

## 🪐 What is BagBot?

BagBot is a 7×24 unattended Python daemon built on the **live Orbio
gateway API** (5 tools, schema verified against production 2026-09-08):

1. **Monitors** your spendable balance via `orbio_get_balance` (every 5 min) — in the gateway model the balance IS the quota
2. **Creates** the key the moment your account has none (`orbio_create_key`) — a key is free; it just spends the balance
3. **Watches** key health via `orbio_get_key_status` (per-account, no key id needed)
4. **Rotates** on age hygiene — `orbio_create_key` again retires the old key atomically
5. **Revokes** on leak detection — if the burn rate spikes (`orbio_revoke_key`), then recreates on the next tick
6. **Cleans up** legacy pre-gateway Orbio keys with a refund (`orbio_delete_key`)
7. **Alerts** when the spendable balance runs low — "hold more $ORBIO"
8. **Reports** everything to WeChat / Feishu / Email / Webhook in **Chinese** + a local dashboard
9. **Runs as a service** via `launchd` (macOS) / `systemd` (Linux)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│                 BagBot                       │
├──────────────────────────────────────────────┤
│  ┌────────────┐    ┌──────────────────────┐  │
│  │   Daemon   │───▶│  Orbio MCP Client    │  │
│  │  (asyncio) │    │  (5 tools wrapper)   │  │
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
make install          # creates .venv, installs deps, copies .env.example → .env

# 2. See it work — zero-config, no token needed
python scripts/demo_e2e.py    # 5-tick end-to-end demo (mock MCP, prints everything)

# 3. Configure (only needed to connect to real Orbio)
vim .env             # fill in ORBIO_MCP_TOKEN + ORBIO_WALLET (+ a notifier)

# 4. Verify
make test            # 97 unit + integration tests, ~45s
make probe           # exercises all 6 Orbio MCP tools (real network)

# 5. Start daemon (foreground)
make run
# or, as a 7×24 service:
bash scripts/install_launchd.sh    # macOS
bash scripts/install_systemd.sh    # Linux
```

> **First time?** Run `python scripts/demo_e2e.py` before touching `.env` —
> it shows the full create → healthy → rotate → revoke → alert loop with zero setup.

---

## 🇨🇳 中文用户教程

完整中文实操指南: [`docs/guide.zh-CN.md`](docs/guide.zh-CN.md)

---

## 📦 Project structure

| File | What it does |
|---|---|
| `src/bagbot/orbio_mcp.py` | Async client wrapping all 6 Orbio MCP tools (with retry) |
| `src/bagbot/daemon.py` | Core 7×24 event loop (monitor → decide → act → report) |
| `src/bagbot/policy.py` | Pure-function decision engine (CLAIM/TOPUP/ROTATE/DELETE/ALERT) |
| `src/bagbot/state.py` | SQLite state store (keys, balances, events) |
| `src/bagbot/notifier.py` | 4 notifier adapters (Feishu, WeChat, Webhook, SMTP), Chinese templates |
| `src/bagbot/dashboard.py` | FastAPI web UI (Chinese-first, dark theme) |
| `scripts/install_launchd.sh` | One-command macOS service install |
| `scripts/install_systemd.sh` | One-command Linux service install |
| `scripts/mutation_test.py` | Crash-safe mutation tester (used in CI nightly) |
| `tests/test_*.py` | 80 tests across 8 modules (~30s, parallel) |
| `docs/guide.zh-CN.md` | 283-line Chinese user guide |
| `docs/BUILD_WEEK.md` | Pre-filled Build Week application text |
| `skills/bagbot/` | **Installable Agent Skill** (SKILL.md + zero-config Python facades) |
| `scripts/install_skill.sh` | One-command skill installer → Claude/Codex/Gemini/agents skill dirs |
| `CHANGELOG.md` | Version history with bug-fix attribution |
| `pyproject.toml` | ruff + mypy + pytest configuration |

### 🧩 Install as an Agent Skill

BagBot also ships as an [Agent Skill](skills/bagbot/SKILL.md) that any LLM
agent (Claude Code, Codex, Gemini CLI, or a generic agent runtime) can pick
up:

```bash
bash scripts/install_skill.sh        # symlinks into ~/.claude/skills, ~/.codex/skills, …
# or target one: SKILL_DEST=~/.claude/skills bash scripts/install_skill.sh
```

Once installed, an agent can use the skill's zero-config facades:

```bash
PYTHONPATH=skills/bagbot/scripts python3 skills/bagbot/scripts/bagbot_cli.py decide 10.0
# → action: create |  reason: no key yet; creating (key is free, spends balance)
```

---

## ✅ Quality bar

| Tool | Status | Where |
|---|---|---|
| **Unit + integration tests** | 80 passing, ~30s | `tests/`, runs in CI on Python 3.10/3.11/3.12 |
| **Mutation testing** | nightly, score: policy 92.9% / daemon 94.1% | `scripts/mutation_test.py`, runs in CI nightly |
| **Ruff lint** | passing | `pyproject.toml` (`[tool.ruff.lint]`) |
| **MyPy type check** | passing | `pyproject.toml` (`[tool.mypy]`) |
| **Shellcheck** | passing | `.github/workflows/ci.yml` |
| **Pre-commit safety** | secrets in `.gitignore`, MCP secrets redacted in CLI output | `_redact()` in `src/bagbot/cli.py` |

Run all checks locally:

```bash
make test                                    # 80 tests
ruff check src/ tests/                       # lint
mypy src/                                    # type check
python scripts/mutation_test.py --module policy   # ~90s
```

---

## 🎯 Built for Orbio Build Week

This project was built in 7 days for [Orbio Build Week](https://orbio.so/build)
(7-day competition, 8M `$ORBIO` prize, 10 winners).

**Builder**: [@keyneszeng](https://github.com/keyneszeng) · X: [@keyneszeng](https://x.com/keyneszeng)
**Live project**: [github.com/keyneszeng/bagbot](https://github.com/keyneszeng/bagbot)

---

## 📜 License

MIT — take anything. Same as [orbio-starter](https://github.com/aster2709/orbio-starter).
