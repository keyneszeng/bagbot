# 📋 BagBot 推文 — 复制即用

> 5 个版本 · 全部字数已验证 · 按场景用

---

## v1.0 英文版（240/280 字符）
**用途**：Build Week 申请主推 / 官方提交后立刻发

```
Built BagBot for @orbiodotso Build Week 🪐

A 7×24 daemon that watches your $ORBIO balance, auto-claims/tops-up/rotates/deletes OpenRouter keys, and notifies in Chinese.

83 tests · 92.9% mutation score · MIT

github.com/keyneszeng/bagbot

$ORBIO
```

---

## v1.0 中文版（242/280 字符）
**用途**：中文圈正式版 · 同一日 +6h 时差友好时段发

```
给 @orbiodotso Build Week 提交了 BagBot 🪐

一个 7×24 守护进程:
• 每 5 分钟看 $ORBIO 余额
• 自动 claim / topup / rotate / delete OpenRouter key
• 飞书/企业微信/邮件/webhook 中文通知
• 中文 web 仪表盘 + 24h 趋势图

MIT · 83 测试 · 92.9% mutation score

github.com/keyneszeng/bagbot

$ORBIO
```

---

## v2.0 英文版（222/280 字符）
**用途**：个人 timeline viral · 第二天发

```
My AI agent now funds itself.

Watches my $ORBIO bag → claims an OpenRouter key → runs the agent → tops up → rotates when old.

No 3am "key ran out" panic.

Built for @orbiodotso Build Week.
github.com/keyneszeng/bagbot

$ORBIO
```

---

## v2.0 中文版（181/280 字符）
**用途**：中文 timeline viral · 第四天发

```
过去一周搭了一个 7×24 AI 守护进程。

它盯着我的 $ORBIO 钱包 → 自动领 OpenRouter key → 喂 AI agent → 烧完了自己充 → 旧了自己换。

我的 AI agent 现在自己养自己。

凌晨 3 点不会再"啊 key 又没了"。

github.com/keyneszeng/bagbot

$ORBIO @orbiodotso
```

---

## v3.0 DM 给 @0x_aster（无字符限制）
**用途**：直接 DM 联合创始人 · 第二天

```
Hi 0x_aster 👋

Just submitted BagBot for Build Week — a self-funding AI daemon on top of the Orbio MCP.

Pitch: most "AI agent" demos still need a human topping up their OpenRouter key. BagBot closes that loop. The agent funds itself from $ORBIO holdings, claims/rotates keys automatically, and notifies in Chinese for the CN community.

83 tests, 92.9% mutation score, MIT, public from day 1.
github.com/keyneszeng/bagbot

What would make this Build-Winnable for you? 🪐
```

---

## v4.0 线程版（4 段，依次发）
**用途**：深度 reach · 第三天发

### 1/4（258/280）— Hook
```
Orbio lets you earn LLM credits just by holding $ORBIO.

But somebody still has to:
• claim the key
• watch the balance
• top it up
• rotate it when it gets old

So I built BagBot — an AI daemon that does all of it, in Chinese. A thread 🧵

$ORBIO @orbiodotso
```

### 2/4（270/280）— Tech
```
BagBot wraps all 6 Orbio MCP tools + runs 7×24:

1. get_balance every 5 min
2. get_key_status for the current key
3. policy decides CLAIM/TOPUP/ROTATE/DELETE
4. Execute + SQLite log + notify

83 tests · 92.9% mutation score on the policy module.

github.com/keyneszeng/bagbot
```

### 3/4（230/280）— Self-funding 故事
```
The kicker: notifiers are Chinese-first.

Feishu webhook ✅
WeChat Work corp app ✅
Email (SMTP) ✅
Generic webhook (Slack/Discord/DingTalk) ✅

So a Chinese dev's AI agent can run on Orbio without ever touching the English dashboard.
```

### 4/4（257/280）— CTA
```
Repo is public, MIT, ships with:
• Chinese user guide (283 lines)
• launchd / systemd install scripts
• Pre-filled Build Week application text
• Crash-safe mutation tester for contributors

Try it: github.com/keyneszeng/bagbot

Built for @orbiodotso Build Week 🪐
```

---

## v5.0 中文跨平台版（小红书 / 微博 / 即刻）
**用途**：中文平台长文 · 第五天

```
🪐 给我的 AI agent 装了一个"自动赚钱"模块

之前每次让 Claude Code 跑大任务，我都要半夜爬起来给它充 OpenRouter key。

直到我用了 @orbiodotso 的 $ORBIO:
- 持币自动赚 LLM 信用
- 我写了一个 daemon (BagBot):
  - 每 5 分钟看一眼余额
  - 自动领 key
  - 烧完了自动充值
  - key 旧了自动换
  - 用中文告诉我进度

凌晨 3 点，我的 AI agent 在自己跑、自己付费、自己续命。

我只需要睡觉。

开源 MIT: github.com/keyneszeng/bagbot
@orbiodotso #OrbioBuildWeek
```

---

## 📅 推荐发布节奏

| 顺序 | 时间 | 推文 |
|---|---|---|
| 1 | T+0h | v1.0 英文 |
| 2 | T+6h | v1.0 中文 |
| 3 | T+1d | DM v3.0 给 @0x_aster |
| 4 | T+1d | v2.0 英文 |
| 5 | T+2d | v4.0 1→2→3→4 thread |
| 6 | T+4d | v2.0 中文 |
| 7 | T+5d | v5.0 跨平台 |

---

## 💬 常见追问回复模板

**"What does it actually do?"**
```
BagBot watches your $ORBIO bag every 5 minutes. When your current OpenRouter key is running low, it auto-claims a fresh one funded by your $ORBIO earnings. When the key is 80% spent, it tops up the same secret. When the key is 7 days old or the burn rate is suspicious, it rotates to a new secret. When a key leaks, it kills the key. And it tells you all of this in Chinese on Feishu/WeChat/Email.
```

**"Why Chinese-first?"**
```
Two reasons. (1) I'm a Chinese-speaking builder and 80% of my AI dev friends are in CN. (2) Orbio doesn't have CN coverage yet — building the CN bridge is a real product gap. If a Chinese dev's Claude Code / Codex agent can run on Orbio without ever seeing an English dashboard, that's the unlock.
```

**"Is it production-ready?"**
```
For a 7-day prototype: yes. 83 tests, 92.9% mutation score on the decision engine, mypy clean, ruff clean, CI matrix on 3 Python versions, nightly mutation testing. The pre-launch checklist you'd want from a serious project, applied to a hackathon entry.
```

**"How do I try it?"**
```
git clone github.com/keyneszeng/bagbot
make install
cp .env.example .env  # fill in ORBIO_MCP_TOKEN + ORBIO_WALLET
make probe
Make sure you hold ≥1,000 $ORBIO on Robinhood Chain.
```
