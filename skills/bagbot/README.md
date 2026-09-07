# BagBot Agent Skill

> **BagBot** — a self-funding AI daemon skill for any agent.
> Let your `$ORBIO` pay for your LLM costs; let the agent run 7×24 without
> a human topping up its key.

This folder is an **installable skill** that works across agent platforms
(Claude Code, Codex CLI, Gemini CLI, and generic LLM agents). It wraps
[Orbio](https://orbio.so)'s 6-tool MCP interface plus a decision engine
and Chinese-first notifications into a single drop-in directory.

## Install

Run from the repo root:

```bash
bash scripts/install_skill.sh
```

This installs to every agent home it finds:
`~/.claude/skills/bagbot`, `~/.codex/skills/bagbot`, `~/.gemini/skills/bagbot`,
`~/.agents/skills/bagbot`, `~/.cursor/skills/bagbot` (symlinked, so the repo
stays the single source of truth).  Target a single home with:

```bash
SKILL_DEST=~/.claude/skills bash scripts/install_skill.sh
```

Or install manually by copying this whole `bagbot/` directory to
`<your-agent>/skills/bagbot/` so its `SKILL.md` is picked up.

### No-install usage (any Python agent)

```bash
export ORBIO_WALLET=0xYourWallet
export ORBIO_MCP_TOKEN=your-bearer-token
PYTHONPATH=skills/bagbot/scripts python3 skills/bagbot/scripts/bagbot_cli.py probe
```

### Pip install (optional)

```bash
cd skills/bagbot/scripts && pip install -e .
```

## Contents

```
bagbot/
├── SKILL.md            # The skill definition (agent-readable instructions)
├── README.md           # this file
├── scripts/            # zero-config Python facades (see scripts/README.md)
│   ├── bagbot_bootstrap.py
│   ├── bagbot_orbio.py         # OrbioClient — 6 MCP tools
│   ├── bagbot_policy.py        # decide() pure-function policy
│   ├── bagbot_settings.py      # .env loader
│   ├── bagbot_cli.py           # probe / status / decide subcommands
│   └── pyproject.toml
├── examples/           # runnable examples (claim_and_use, decide_demo)
└── references/         # pointers to full docs in the main repo
```

## Config (see SKILL.md for the full table)

`ORBIO_WALLET`, `ORBIO_MCP_TOKEN` (both required), plus policy knobs
(`LOW_BALANCE_USD`, `TOPUP_THRESHOLD`, `ROTATE_MAX_AGE_HOURS`,
`ROTATE_BURST_USD_PER_HOUR`, `KEY_CAP_USD`) and optional notifier creds
(Feishu / WeChat Work / SMTP / webhook).

> **Security**: `ORBIO_MCP_TOKEN` can mint every key your holdings can pay
> for — treat it like a wallet private key. Never commit it, never print it.
> CLI output auto-redacts `secret`/`token`/`authorization` fields.

## More docs

- Main repository: https://github.com/keyneszeng/bagbot
- Chinese user guide: `../../docs/guide.zh-CN.md`
- Orbio: https://orbio.so · Build Week: https://orbio.so/build

## License

MIT.
