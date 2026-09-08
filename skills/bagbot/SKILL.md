---
name: bagbot
description: >
  MUST USE when the task involves Orbio ($ORBIO), Orbio gateway keys,
  agent self-funding, LLM inference credits, or running an AI agent without
  a human topping up its key — e.g. auto-create / rotate / revoke the Orbio
  key from $ORBIO holdings, monitor the spendable balance, or set up
  Chinese-first notifications (Feishu / WeChat Work / Email / Webhook).

  在以下情况使用：任务涉及 Orbio($ORBIO)、Orbio gateway key、让 AI agent
  自养（self-funding）、LLM 推理额度、自动创建/轮换/撤销 key、监控可花余额、
  或配置中文通知（飞书/企业微信/邮件/webhook）。

  NOT for: 支付预言机/MPP/x402 一类的链上自动支付（那是 x402/Internet Court）；
  只查询 $ORBIO 币价行情。本技能专注 "Orbio 持币 → LLM 推理额度 → agent 自己管 key"。
license: MIT
repo: https://github.com/keyneszeng/bagbot
version: 0.2.0
metadata:
  homepage: https://orbio.so/build
  languages: [en, zh-CN]
  compatibility: [claude-code, codex, gemini-cli, generic-llm]
  category: devops
  tags: [orbio, openrouter, ai-agent, mcp, self-funding, daemon, llm-costs]
---

# BagBot — Self-funding AI daemon / 让 AI agent 自己管钱

> Orbio 让你持币赚 LLM 额度，但还是要有人管 key、盯余额、换旧 key。
> BagBot 是第一个把这些脏活累活完全自动化、并支持中文通知的 daemon。
> 你的 Agent 不再需要你充钱，它会自己管自己。

**Gateway 模型**（2026-09-08 生产环境实测）：key 本身不带额度，
它逐笔直接花账户的**可花余额（balance）**。所以策略非常简单——
没 key 就建（免费）、key 老了就原子换新、余额燃烧异常就撤销、
余额低了就提醒你多持点 $ORBIO。

## 何时使用 When to use

- 你的 agent（Claude Code / Codex / 自写脚本）需要 LLM 推理额度，且你持有或想持有 `$ORBIO`；
- 你想让 agent **长期无人值守**运行：没 key 自动建、超龄自动换、疑似泄露自动撤销；
- 你需要把 Orbio 的 "持币生 LLM 额度" 变成可编程调用（MCP 5 工具）；
- 你需要在飞书/企业微信/邮件收中文告警。

## 前置 Prerequisites

1. 一个持有 ≥1,000 `$ORBIO` 的钱包地址；
2. 从 [orbio.so](https://orbio.so) 或 Orbio MCP 登录流程拿到的 **Bearer token**（= ORBIO_MCP_TOKEN）；
3. Python ≥3.10（本技能的 scripts 只依赖标准库 + httpx/pydantic/python-dotenv，均可按需 pip 安装）。

## 目录结构 Layout

```
skills/bagbot/
├── SKILL.md                 本文件
├── scripts/                 # 自包含、零安装 Python 助手（任意 agent 可直接 import）
│   ├── bagbot_orbio.py      # 5 个 MCP 工具客户端（facade → 主包）
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
        print("spendable USD:", bal.unclaimed_usd)  # 余额即额度
        st = await c.get_key_status()               # 按账户查，无参数
        print("has key:", st.has_key, st.prefix)
        if not st.has_key:
            key = await c.create_key(label="my-box")
            print("prefix:", key.prefix)   # secret 只显示这一次，立即保存！

asyncio.run(main())
PY
```

### 方式 B：作为 pip 包安装

```bash
cd skills/bagbot/scripts
pip install -e .          # 提供 `bagbot` console script
bagbot probe              # 只读探测 get_balance + get_key_status
bagbot status
```

### 方式 C：完整 daemon（7×24 常驻，含通知/仪表盘）

```bash
# 在主仓库根目录
make install && cp .env.example .env  # 填 ORBIO_WALLET + ORBIO_MCP_TOKEN
make demo                             # 零凭证看 5 幕决策闭环
make run                              # 或 scripts/install_launchd.sh / systemd
```

## 核心 Python API（5 工具，全部实测于生产）

| 函数 | 说明 |
|---|---|
| `await c.get_balance()` → Balance | 可花余额 / 累计赚取 / 累计消耗（**余额即额度**）|
| `await c.get_key_status()` → KeyStatus | 按账户查 key（无参数）：hasKey / prefix / createdAt / lastUsedAt / legacy |
| `await c.create_key(label="...")` → Key | 创建（或原子轮换）key；`key.secret` **只显示一次**；`label` ≤60 字符 |
| `await c.revoke_key()` → RevokeResult | 撤销当前 key（余额不受影响）|
| `await c.delete_key()` → DeleteResult | 仅清理 legacy 旧版 key（未用额度退回）|

决策引擎（纯函数，可单测）：

```python
from bagbot_policy import decide, PolicyConfig
from bagbot_policy import Snapshot

snap = Snapshot(
    has_key=False, key_prefix=None, key_age_hours=0.0,
    spend_rate_usd_per_hour=0.0, balance_usd=10.0,
    accrued_usd=100.0, last_used_at=None, has_legacy_key=False,
)
action, reason = decide(snap, PolicyConfig())
# Action.CREATE  "no key yet; creating (key is free, spends balance)"
```

决策优先级：REVOKE（燃烧率 ≥ 阈值，疑似泄露）→ CREATE（没 key，永远建）
→ CREATE（key 超龄原子轮换）→ DELETE（legacy 清理）→ ALERT（余额偏低）
→ NOTHING。

## 环境变量 Environment

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `ORBIO_WALLET` | ✅ | — | 持有 $ORBIO 的钱包地址 |
| `ORBIO_MCP_TOKEN` | ✅ | — | Orbio MCP Bearer token（=你的账户控制权，务必保密）|
| `ORBIO_MCP_URL` | | `https://www.orbio.so/api/mcp` | MCP 端点 |
| `LOW_BALANCE_USD` | | `5.0` | 可花余额低于此值触发 ALERT |
| `ROTATE_MAX_AGE_HOURS` | | `168` | key 超过 N 小时自动原子轮换（0=禁用）|
| `ROTATE_BURST_USD_PER_HOUR` | | `20.0` | 余额燃烧速率超此值自动 REVOKE |
| `LANGUAGE` | | `zh-CN` | 通知语言（zh-CN / en）|

通知渠道（可选，任一开启即可）：`FEISHU_WEBHOOK_URL` / `FEISHU_SECRET`、
`WECHAT_CORP_ID`+`WECHAT_AGENT_ID`+`WECHAT_SECRET`、
`WEBHOOK_URL`、`SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`EMAIL_FROM`/`EMAIL_TO`。

## 安全 Security

- `ORBIO_MCP_TOKEN` 能代你创建/撤销 key、花光余额 —— **等同钱包私钥级别**。绝不提交进 git、绝不外发。
- `key.secret` 由 `orbio_create_key` **只返回一次**；`bagbot` CLI 与示例输出对 `secret/token/authorization/api_key/password` 等字段自动 `***REDACTED***`。
- 怀疑泄露：立即 `revoke_key`（余额无损）或在 orbio.so 撤销 token。

## 常见排错 Troubleshooting

| 现象 | 处理 |
|---|---|
| probe 卡在 retry | 检查 `ORBIO_MCP_URL` 可达性与 token 有效性（OAuth token 会过期，重新登录拿新的）|
| 308 Permanent Redirect 循环 | 端点 URL 不要带尾部斜杠；本客户端已改用绝对 URL 修复 |
| 通知没到 | 检查对应 webhook/SMTP 配置与 `LANGUAGE` |
| key 用不了 | 确认用的是 `key.base_url` + `key.secret`；余额是否足够 |

## 更多文档 More docs

- 完整中文实操指南：[docs/guide.zh-CN.md](../../docs/guide.zh-CN.md)（主仓库）
- 主 README：[README.md](../../README.md)
- Orbio 官网：[orbio.so](https://orbio.so) · Build Week：[orbio.so/build](https://orbio.so/build)
