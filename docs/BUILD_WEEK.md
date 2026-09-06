# Orbio Build Week Submission — BagBot

> Pre-filled application text for the [Orbio Build Week](https://orbio.so/build) form.
> Copy each block into the corresponding field on orbio.so/build.

---

## Field: Project name

```
BagBot
```

## Field: One-line tagline

```
The first self-funding, self-healing AI daemon for agents on Orbio — with Chinese notifications built in.
```

## Field: What are you building? (long description)

```
Orbio lets you earn LLM credits just by holding tokens — but somebody still has to claim keys, watch balances, and rotate old ones.  BagBot is the first open-source daemon that fully automates the entire credit lifecycle — monitoring, claiming, topping up, rotating, deleting — and ships with Chinese-language notifications out of the box, because the Orbio ecosystem has zero Chinese coverage today.

A single Python process runs forever:
  • Every 5 minutes it polls orbio_get_balance and orbio_get_key_status
  • When the unclaimed balance passes a threshold, it claims a fresh OpenRouter key automatically
  • When a key is 80% spent, it tops up the same secret (no key churn for downstream callers)
  • When the key is too old, or its burn rate is suspicious, it rotates the secret (old dies, new inherits the credit)
  • Every action is written to a local SQLite ledger, broadcast to Feishu / WeChat / Email / Webhook with a Chinese template, and reflected in a Chinese-first web dashboard

It's built on the same 6 MCP tools anyone can call from Claude Code, but it's a long-running daemon — the part the official starter kit doesn't cover.  The dashboard ships a balance trend chart, event log, and one-click manual claim/rotate/topup.

The differentiator is operational:  the Orbio MCP gives agents the tools to be self-funding, but the loop has to actually be closed by *something*.  BagBot closes it, and it does so in a way that fits how Chinese builders actually run services (Feishu, WeChat Work, macOS launchd, no English-only documentation).
```

## Field: Which MCP tools does your project use?

```
✅ orbio_get_balance
✅ orbio_claim_key
✅ orbio_get_key_status
✅ orbio_top_up_key
✅ orbio_rotate_key
✅ orbio_delete_key
```

## Field: GitHub repository

```
https://github.com/keyneszeng/bagbot
```

## Field: How will the project be made public by day 7?

```
Public from day 1.  MIT licensed.  Repository will include:
  - Full source under src/bagbot/
  - Chinese user guide at docs/guide.zh-CN.md
  - Bilingual README
  - macOS launchd + Linux systemd install scripts (one command each)
  - Working demo video showing the dashboard + a real claim → topup → rotate cycle
```

## Field: Anything else we should know?

```
I'm keyneszeng — the author of ChatMemOllama (https://github.com/keyneszeng/ChatMemOllama), an open-source WeChat AI bot that hit 7 forks and is still my most-cited project.  I run aibuild.work, a Chinese-language AI curriculum with 5 learning tracks.

BagBot is what happens when ChatMemOllama grows up: instead of using local Ollama models on a single Mac, it now uses Orbio-derived OpenRouter credits, and the agent itself keeps the credits topped up.  The same audience (Chinese creators who want their AI bot to "just work" 24/7) is who I built this for, and they happen to be the audience Orbio has not reached yet.

If BagBot wins or places, I will:
  1. Add a free chapter to aibuild.work's "AI 工作提效实战营" teaching the Orbio MCP setup
  2. Maintain BagBot for at least 6 months
  3. Open a Chinese-language Orbio community channel
```
