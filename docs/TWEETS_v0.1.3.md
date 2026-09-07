# BagBot 推文 — v0.1.3 更新版

> 基于 v0.1.3 代码更新重新编写的推文草稿。
> **新素材**：Dashboard 鉴权漏洞发现+修复 · 97 tests · dashboard.py 100% mutation score · Agent Skill 一键安装。
>
> 所有字数已按 X 规则验证（URL t.co = 23 字符，全部 ≤275 留缓冲）。

---

## 📋 已发布（跳过，勿重发）

- ✅ Day1: v1.0 英文版
- ✅ Day2: v2.0 英文故事版
- ✅ Day2: DM 给 @0x_aster

---

## 🎯 接下来推荐发布顺序

| 优先级 | 推文 | 时机 |
|---|---|---|
| 1 | **EN day3 progress**（v0.1.3 里程碑） | 立即 |
| 2 | **ZH bug story**（中文版漏洞故事） | EN 后 +6h |
| 3 | **EN skill**（Agent Skill 公告） | 次日 |
| 4 | **ZH skill** | EN skill 后 +6h |
| 5 | **EN / ZH thread hook**（线程入口，可后接 3 条旧 v4.0 的 2/3/4） | 之后 |

---

## 1️⃣ EN day3 progress — v0.1.3 里程碑（255/275）

```
Day 3: BagBot hits v0.1.3 🚀

Found an auth bug in my own code, fixed it, wrote 13 mutation-resistant tests. dashboard.py: 100% mutation score. 97 tests total.

Now installs as an Agent Skill (Claude Code / Codex / Gemini).

github.com/keyneszeng/bagbot

$ORBIO
```

## 2️⃣ EN bug story — 漏洞故事（271/275）

```
Found a real bug in my own hackathon project 🚨

Endpoints that mint OpenRouter keys had NO auth — anyone reaching the port could drain your $ORBIO.

v0.1.3: DASHBOARD_TOKEN now gates every mutation.

97 tests · dashboard 100% mutation · MIT
github.com/keyneszeng/bagbot
$ORBIO
```

## 3️⃣ EN skill — Agent Skill 公告（265/275）

```
BagBot is now an Agent Skill 🧩

One command installs into Claude Code / Codex / Gemini / Cursor:

bash scripts/install_skill.sh

Your agent self-funds from $ORBIO: claim → run → top up → rotate → delete.

97 tests · MIT · github.com/keyneszeng/bagbot

$ORBIO @orbiodotso
```

## 4️⃣ ZH bug — 中文漏洞故事（197/275）

```
给自己项目挖了个真 bug，修好了 🚨

铸 OpenRouter key 的 dashboard 接口居然没鉴权——谁摸到端口都能从你 $ORBIO 铸 key。

v0.1.3：写操作全部要求 DASHBOARD_TOKEN。

97 测试 · dashboard 100% mutation · MIT
github.com/keyneszeng/bagbot
$ORBIO @orbiodotso
```

## 5️⃣ ZH skill — 中文 Skill 公告（206/275）

```
BagBot 现在是一键安装的 Agent Skill 🧩

bash scripts/install_skill.sh

Claude Code / Codex / Gemini / Cursor 通用。你的 agent 自己靠 $ORBIO 自养：领 key → 干活 → 充值 → 轮换。

97 测试 · MIT · github.com/keyneszeng/bagbot

$ORBIO @orbiodotso
```

## 6️⃣ EN thread hook — 线程入口（230/275）

```
Orbio pays you LLM credits for holding $ORBIO.

But someone has to claim keys, watch balances, top up, rotate.

I built BagBot — an AI daemon that does all of it. Chinese-first. Thread 🧵

github.com/keyneszeng/bagbot
$ORBIO @orbiodotso
```

## 7️⃣ ZH thread hook — 中文线程入口（134/275）

```
Orbio 让你持币就赚 LLM 额度。

但总得有人：领 key、盯余额、充值、轮换。

我做了 BagBot —— 全部自动化的 AI daemon + 中文通知。

线程 🧵

github.com/keyneszeng/bagbot
$ORBIO @orbiodotso
```

---

## 🔄 后续线程主体（沿用 v4.0 旧版 2/3/4，数字已更新）

**Thread 2/4 — Tech**
```
BagBot wraps all 6 Orbio MCP tools + runs 7×24:

1. get_balance every 5 min
2. get_key_status for the current key
3. policy decides CLAIM/TOPUP/ROTATE/DELETE
4. Execute + SQLite log + notify

97 tests · dashboard.py 100% mutation score.

github.com/keyneszeng/bagbot
```

**Thread 3/4 — Chinese-first**
```
The kicker: notifiers are Chinese-first.

Feishu webhook ✅
WeChat Work corp app ✅
Email (SMTP) ✅
Generic webhook (Slack/Discord/DingTalk) ✅

So a Chinese dev's AI agent runs on Orbio without touching the English dashboard.
```

**Thread 4/4 — CTA**
```
Repo is public, MIT, ships with:
• Chinese user guide (283 lines)
• launchd / systemd install scripts
• Agent Skill (one-line install)
• Crash-safe mutation tester for contributors

Try it: github.com/keyneszeng/bagbot

Built for @orbiodotso Build Week 🪐
```

---

## ⚠️ 备注

- 数字已校准到 v0.1.3：**97 tests**、dashboard.py **100% mutation**（旧版说 83 tests / 92.9% policy，发布时别再用旧数字）
- Agent Skill 是 v0.1.3 新增的强差异化点（别的 builder 大概率没有"安装即用的 agent skill"）
- 漏洞故事是「我发现了自己代码的漏洞并修复」—— 工程严谨性的有力叙事，比单纯晒数字更能打
