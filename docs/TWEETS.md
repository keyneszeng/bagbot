# BagBot — Build Week 推文草稿

5 个版本，按场景使用。所有版本都已数过字数（X 限制 280 字符，URL 算 23 个）。

## 📋 快速决策表

| 你想…… | 用这个 |
|---|---|
| 提交 Build Week 时发个正式介绍 | v1.0 英文版 |
| 同时给中文圈也来一份 | v1.0 中文版 |
| 发到个人 timeline 想要 viral | v2.0 故事版（英/中任选） |
| 想让评委亲自看到 → DM @0x_aster | v3.0 DM |
| 想要深度 reach（4 段） | v4.0 线程版 |
| 跨平台到小红书/微博/即刻 | v5.0 中文跨平台版 |

> 推文里所有 `github.com/keyneszeng/bagbot` 在 X 上算 23 字符（短链规则）。
> DM 没有字符限制，可以写得详细。

---

## v1.0 — **正式版**（Build Week 申请主推）

**英文版** (240/280 字符)
```
Built BagBot for @orbiodotso Build Week 🪐

A 7×24 daemon that watches your $ORBIO balance, auto-claims/tops-up/rotates/deletes OpenRouter keys, and notifies in Chinese.

83 tests · 92.9% mutation score · MIT

github.com/keyneszeng/bagbot

$ORBIO
```

**中文版** (242/280 字符)
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

## v2.0 — **故事版**（适合个人 timeline，更易病毒）

**英文版** (222/280 字符)
```
My AI agent now funds itself.

Watches my $ORBIO bag → claims an OpenRouter key → runs the agent → tops up → rotates when old.

No 3am "key ran out" panic.

Built for @orbiodotso Build Week.
github.com/keyneszeng/bagbot

$ORBIO
```

**中文版** (181/280 字符)
```
过去一周搭了一个 7×24 AI 守护进程。

它盯着我的 $ORBIO 钱包 → 自动领 OpenRouter key → 喂 AI agent → 烧完了自己充 → 旧了自己换。

我的 AI agent 现在自己养自己。

凌晨 3 点不会再"啊 key 又没了"。

github.com/keyneszeng/bagbot

$ORBIO @orbiodotso
```

---

## v3.0 — **DM 候选**（给 @0x_aster 的私聊开场白）

```
Hi 0x_aster 👋

Just submitted BagBot for Build Week — a self-funding AI daemon on top of the Orbio MCP.

Pitch: most "AI agent" demos still need a human topping up their OpenRouter key. BagBot closes that loop. The agent funds itself from $ORBIO holdings, claims/rotates keys automatically, and notifies in Chinese for the CN community.

83 tests, 92.9% mutation score, MIT, public from day 1.
github.com/keyneszeng/bagbot

What would make this Build-Winnable for you? 🪐
```

---

## v4.0 — **线程版**（4-tweet thread，适合 viral reach）

**1/4 — Hook** (254 字符)
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

**2/4 — Tech** (270 字符)
```
BagBot wraps all 6 Orbio MCP tools + runs 7×24:

1. get_balance every 5 min
2. get_key_status for the current key
3. policy decides CLAIM/TOPUP/ROTATE/DELETE
4. Execute + SQLite log + notify

83 tests · 92.9% mutation score on the policy module.

github.com/keyneszeng/bagbot
```

**3/4 — The "self-funding" story** (256 字符)
```
The kicker: notifiers are Chinese-first.

Feishu webhook ✅
WeChat Work corp app ✅
Email (SMTP) ✅
Generic webhook (Slack/Discord/DingTalk) ✅

So a Chinese dev's AI agent can run on Orbio without ever touching the English dashboard.
```

**4/4 — CTA** (257 字符)
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

## v5.0 — **中文跨平台版**（小红书 / 微博 / 即刻）

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

## 🎯 发推策略

| 顺序 | 时间 | 渠道 | 目的 |
|------|------|------|------|
| 1 | Build Week 申请提交后立刻 | X v1.0 英文版 | 官方可见性 |
| 2 | 同一日 +6h | X v1.0 中文版 | 中文圈 |
| 3 | 次日 | X v2.0 故事版 | 个人 timeline viral |
| 4 | 次日 | DM v3.0 给 @0x_aster | 直接对话 |
| 5 | 第 3 日 | X v4.0 线程版 | 深度 reach |
| 6 | 第 4-5 日 | 小红书/微博 v5.0 | 中文平台 |

## 🏷️ Hashtag 建议

- **英文**：`#OrbioBuildWeek` `#OpenRouter` `#AIAgent` `#selfhosting` `#devtools`
- **中文**：`#AI代理` `#Orbio` `#LLM` `#开源` `#自动化`

## 📊 回复模板（如果有人问）

**"What does it actually do?"**
> BagBot watches your $ORBIO bag every 5 minutes. When your current OpenRouter key is running low, it auto-claims a fresh one funded by your $ORBIO earnings. When the key is 80% spent, it tops up the same secret. When the key is 7 days old or the burn rate is suspicious, it rotates to a new secret. When a key leaks, it kills the key. And it tells you all of this in Chinese on Feishu/WeChat/Email.

**"Why Chinese-first?"**
> Two reasons. (1) I'm a Chinese-speaking builder and 80% of my AI dev friends are in CN. (2) Orbio doesn't have CN coverage yet — building the CN bridge is a real product gap. If a Chinese dev's Claude Code / Codex agent can run on Orbio without ever seeing an English dashboard, that's the unlock.

**"Is it production-ready?"**
> For a 7-day prototype: yes. 83 tests, 92.9% mutation score on the decision engine, mypy clean, ruff clean, CI matrix on 3 Python versions, nightly mutation testing. The pre-launch checklist you'd want from a serious project, applied to a hackathon entry.

**"How do I try it?"**
> git clone github.com/keyneszeng/bagbot
> make install
> cp .env.example .env  # fill in ORBIO_MCP_TOKEN + ORBIO_WALLET
> make probe
> Make sure you hold ≥1,000 $ORBIO on Robinhood Chain.
