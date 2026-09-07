---
name: bagbot
description: >
  MUST USE when the task involves Orbio ($ORBIO), OpenRouter API keys, agent
  self-funding, LLM inference credits, or running an AI agent without a human
  topping up its key — e.g. auto-claim / top-up / rotate / delete OpenRouter
  keys from $ORBIO holdings, monitor a balance, or set up Chinese-first
  notifications (Feishu / WeChat Work / Email / Webhook).

  在以下情况使用：任务涉及 Orbio($ORBIO)、OpenRouter API key、让 AI agent
  自养（self-funding）、LLM 推理额度、自动领取/充值/轮换/销毁 OpenRouter key、
  监控余额、或配置中文通知（飞书/企业微信/邮件/webhook）。

  NOT for: 支付预言机/MPP/x402 一类的链上自动支付（那是 x402/Internet Court）；
  只查询 $ORBIO 币价行情。本技能专注 "Orbio 持币 → LLM 推理额度 → agent 自己管 key"。
license: MIT
repo: https://github.com/keyneszeng/bagbot
version: 0.1.2
metadata:
  homepage: https://orbio.so/build
  languages: [en, zh-CN]
  compatibility: [claude-code, codex, gemini-cli, generic-llm]
  category: devops
  tags: [orbio, openrouter, ai-agent, mcp, self-funding, daemon, llm-costs]
---

# BagBot — Self-funding AI daemon / 让 AI agent 自己管钱

> Orbio 让你持币赚 LLM 额度，但还是要有人 claim key、watch 余额、rotate 旧 key。
> BagBot 是第一个把这些脏活累活完全自动化、并支持中文通知的 daemon。
> 你的 Agent 不再需要你充钱，它会自己管自己。

## 何时使用 When to use

- 你的 agent（Claude Code / Codex / 自写脚本）需要 OpenRouter key，且你持有或想持有 `$ORBIO`；
- 你想让 agent **长期无人值守**运行：key 烧完自动充值、快到期自动轮换、泄露自动销毁；
- 你需要把 Orbio 的 "持币生 LLM 额度" 变成可编程调用（MCP 6 工具）；
- 你需要在飞书/企业微信/邮件收中文告警。

## 前置 Prerequisites

1. 一个持有 ≥1,000 `$ORBIO` 的 Robinhood Chain 钱包地址；
2. 从 [orbio.so](https://orbio.so) 或 Orbio MCP 登录流程拿到的 **Bearer token**（= ORBIO_MCP_TOKEN）；
3. Python ≥3.10（本技能的 scripts 只依赖标准库 + httpx/pydantic/python-dotenv，均可按需 pip 安装）。

## 目录结构 Layout

```
skills/bagbot/
├── SKILL.md                 本文件
├── scripts/                 # 自包含、零安装 Python 助手（任意 agent 可直接 import）
│   ├── bagbot_orbio.py      # 6 个 MCP 工具客户端
│   ├── bagbot_policy.py     # 纯函数决策引擎
│   ├── bagbot_settings.py   # .env 加载
│   └── __init__.py
├── examples/                # 可直接运行示例
└── references/              # 详细指南链接（相对主仓库）
```

## 快速开始 Quick Start

### 方式 A：任意 agent 直接 import（零安装）

```bash
PYTHONPATH=skills/bagbot/scripts python3 - <<'PY'
from bagbot_orbio import OrbioClient
import asyncio

async def main():
    # 从环境变量自动读 ORBIO_WALLET / ORBIO_MCP_TOKEN
    async with OrbioClient.from_env() as c:
        bal = await c.get_balance()
        print("unclaimed USD:", bal.unclaimed_usd)
        key = await c.claim_key(cap_usd=10)
        print("key:", key.key_id, "headroom:", key.headroom_usd)
        await c.delete_key(key.key_id)  # 用完销毁

asyncio.run(main())
PY
```

### 方式 B：作为 pip 包安装

```bash
cd skills/bagbot/scripts
pip install -e .          # 提供 `bagbot` console script
bagbot probe              # 遍历 6 个工具，输出脱敏结果
bagbot status
```

### 方式 C：完整 daemon（7×24 常驻，含通知/仪表盘）

```bash
# 在主仓库根目录
make install && cp .env.example .env  # 填 ORBIO_WALLET + ORBIO_MCP_TOKEN
make run                              # 或 scripts/install_launchd.sh / systemd
```

## 核心 Python API

| 函数 | 说明 |
|---|---|
| `await c.get_balance()` → Balance | 未领取信用(USD) / 累计已赚 / 已领取 |
| `await c.claim_key(cap_usd=200)` → Key | 铸造 OpenRouter key（单次 ≤$200，返回 `key.secret`）|
| `await c.get_key_status(key_id)` → KeyStatus | 实时读 OpenRouter 消费（headroom / spend / remaining）|
| `await c.top_up_key(key_id, amount)` → Key | 同一 secret 续额（key 不换）|
| `await c.rotate_key(key_id)` → Key | 换新 secret，旧 key 先失效 |
| `await c.delete_key(key_id)` | 销毁 key，未用额度回余额 |

决策引擎（纯函数，可单测）：

```python
from bagbot_policy import decide, PolicyConfig
from bagbot_policy import Snapshot

snap = Snapshot(
    has_key=False, key_id=None, key_age_hours=0.0,
    spend_rate_usd_per_hour=0.0, key_used_fraction=0.0,
    key_remaining_usd=0.0, unclaimed_usd=10.0,
    earned_usd=20.0, claimed_usd=0.0,
)
action, reason = decide(snap, PolicyConfig())
# Action.CLAIM  "no key yet; balance is enough to claim"
```

## 环境变量 Environment

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `ORBIO_WALLET` | ✅ | — | 持有 $ORBIO 的钱包地址 |
| `ORBIO_MCP_TOKEN` | ✅ | — | Orbio MCP Bearer token（=你的钱包的 key 铸造权，务必保密）|
| `ORBIO_MCP_URL` | | `https://www.orbio.so/api/mcp` | MCP 端点 |
| `LOW_BALANCE_USD` | | `5.0` | 低于此值触发 ALERT/尝试 claim |
| `TOPUP_THRESHOLD` | | `0.80` | key 用到此比例自动 top-up |
| `ROTATE_MAX_AGE_HOURS` | | `168` | key 超过 N 小时自动 rotate（0=禁用）|
| `ROTATE_BURST_USD_PER_HOUR` | | `20.0` | 燃烧速率超此值自动 rotate |
| `KEY_CAP_USD` | | `200.0` | 单次 claim 上限 |
| `LANGUAGE` | | `zh-CN` | 通知语言（zh-CN / en）|

通知渠道（可选，任一开启即可）：`FEISHU_WEBHOOK_URL` / `FEISHU_SECRET`、
`WECHAT_CORP_ID`+`WECHAT_AGENT_ID`+`WECHAT_SECRET`、
`WEBHOOK_URL`、`SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM`/`EMAIL_TO`。

## 安全 Security

- `ORBIO_MCP_TOKEN` 能代你 claim 全部额度 —— **等同钱包私钥级别**。绝不提交进 git、绝不外发。
- `bagbot` CLI 与示例输出对 `secret/token/authorization/api_key/password` 等字段自动 `***REDACTED***`。
- 怀疑泄露：立即 `rotate_key` 或在 orbio.so 撤销 token。

## 常见排错 Troubleshooting

| 现象 | 处理 |
|---|---|
| probe 卡在 retry | 检查 `ORBIO_MCP_URL` 可达性、token 有效性与额度 |
| claim 返回额度不足 | `unclaimed < LOW_BALANCE_USD`，需先靠持仓累积 |
| 通知没到 | 检查对应 webhook/SMTP 配置与 `LANGUAGE` |
| key 用不了 | 确认余额在 key 上、模型走 OpenRouter 路由 |

## 更多文档 More docs

- 完整中文实操指南：[docs/guide.zh-CN.md](../../docs/guide.zh-CN.md)（主仓库）
- 主 README：[README.md](../../README.md)
- Orbio 官网：[orbio.so](https://orbio.so) · Build Week：[orbio.so/build](https://orbio.so/build)
