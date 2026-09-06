# BagBot 中文实操指南

> **Orbio 让你用持币就能赚 LLM 额度,但还是要有人 claim key、watch 余额、rotate 旧 key。
> BagBot 是第一个把这些脏活累活完全自动化、并支持中文通知的 daemon。**
>
> 你的 Agent 不再需要你充钱,它会自己管自己。

本指南面向**中文用户**,会一步步带你把 BagBot 跑起来。

---

## 🪐 这是什么

[Orbio](https://orbio.so/) 是个非常新的产品:你只要把 $ORBIO 存在钱包里,平台就会**每小时**自动把你应得的 LLM 信用发到你账上。听起来很美好对吧?但拿到信用之后,你还得:

1. 自己去仪表盘点 "Claim a key",把信用换成 OpenRouter 的 API key
2. 监控余额,快用完了**再 claim 一次**
3. 万一 key 泄露或被刷,得 **rotate** 一份新 secret
4. 想紧急下线某个 key,得 **delete** 它

这些"运维脏活"在你刚开始玩的时候可以手动点几下,但当你的 **公众号 AI 机器人 / Claude Code / 自动发推 agent** 真的 7×24 在跑的时候,凌晨 3 点它 key 烧完了,公众号粉丝看到的就是一片空白。

**BagBot 就是为了解决这件事**。它是一个 Python 守护进程,常驻后台,**自动监控、自动决策、自动执行、自动通知**。你只管用,它在后台替你管。

---

## 🧰 准备工作

- **Python 3.10+** (macOS / Linux 都行)
- **一个 Robinhood Chain 钱包地址**——里面要持有 ≥ 1,000 $ORBIO(Orbio 2026-09-02 刚把门槛从 10 万降到 1,000)
- **Orbio MCP 的 Bearer Token**——在 Claude Code 里跑 `/mcp` 选 Orbio 并 Authenticate 后,你的 token 会被存到系统 keychain;也可以用 MCP inspector 抓取
- **至少一个通知渠道**(可二选一):
  - 微信公众号 / 企业微信应用(中文用户最方便)
  - 飞书 / Lark 自定义机器人 webhook
  - 通用 webhook(Slack / Discord / 钉钉)
  - 邮件(SMTP)

---

## 🚀 5 分钟跑起来

### Step 1. 下载与安装

```bash
git clone https://github.com/keyneszeng/bagbot.git
cd bagbot
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2. 配置文件

```bash
cp .env.example .env
# 用编辑器打开 .env,改以下几行:
```

```ini
# 必填
ORBIO_WALLET=0xYourRobinhoodChainWalletAddressHere
ORBIO_MCP_TOKEN=orbio-mcp-bearer-token-from-claude-code-mcp-login

# 强烈建议填写通知渠道(选一个就行)
FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxx
```

> 💡 怎么拿 `ORBIO_MCP_TOKEN`?
>
> ```bash
> # 1) 在 Claude Code 里
> claude mcp add --transport http --scope user orbio https://www.orbio.so/api/mcp
> /mcp    # 选 orbio → Authenticate
> # 2) 认证完成后,token 通常存在系统 keychain;
> #    也可以用 MCP inspector 抓 HTTP 请求头里的 Authorization: Bearer ...
> ```

### Step 3. 先跑一次 `probe` 自检

```bash
python -m bagbot.cli probe
```

这个命令会**依次调用 6 个 MCP 工具并打印结果**,帮你确认 token 有效、钱包有余额、MCP 通信正常。

你应该看到类似输出:

```
→ orbio_get_balance
{
  "earned": 12.34,
  "claimed": 8.00,
  "unclaimed": 4.34,
  "currency": "USD"
}

→ orbio_claim_key (cap=10 USD, dry-style probe)
{ "key_id": "k_abc123...", "headroom_usd": 10.0 }

→ orbio_get_key_status
{ "key_id": "k_abc123...", "spend": 1.2, "headroom": 10.0, "remaining": 8.8 }
...
```

> ⚠️ **注意**:`probe` 真的会消耗你的余额来 claim 一个新 key。如果你不想消耗,先跑 `python -m bagbot.cli once` 试一次只读巡检。

### Step 4. 启动守护进程

**前台运行**(看实时日志):

```bash
python -m bagbot.cli run
```

**后台常驻**(macOS launchd):

```bash
bash scripts/install_launchd.sh
```

**后台常驻**(Linux systemd):

```bash
bash scripts/install_systemd.sh
```

### Step 5. 打开仪表盘

默认会在 http://127.0.0.1:8765 启动一个中文 web 仪表盘:

```bash
# 守护进程已经跑的话,直接访问
open http://127.0.0.1:8765

# 也可以独立启动仪表盘(不跑守护进程)
python -m bagbot.cli dashboard
```

仪表盘上你会看到:

- **未领取余额 / 累计赚取 / 已兑换** 三张大数卡片
- **当前 Key 剩余**(实时从 OpenRouter 拉)
- **未领取余额 24h 趋势图**(纯前端 canvas 绘制)
- **事件日志**(claim / rotate / topup / alert)
- **手动操作按钮**(claim / rotate / topup)

---

## 🎯 BagBot 会自动做什么

默认策略(可以在 `.env` 里调):

| 触发条件 | 行为 |
|---|---|
| 没有任何 key 且未领取余额 ≥ $5 | 自动 `claim_key` |
| Key 已用 ≥ 80% 且未领取 ≥ $1 | 自动 `top_up_key`(同一个 secret) |
| Key 持续 7 天(168 小时) | 自动 `rotate_key`(发新 secret) |
| 燃烧速度 > $20/h(异常) | 自动 `rotate_key` 防止被刷 |
| Key 余额耗尽但没钱 topup | 自动 `rotate_key` 切新 key |
| 未领取余额 < $5 持续 5 分钟 | 推送告警通知 |

每次动作都会:
- 写一行到 SQLite
- 推送一条中文通知到你的飞书/微信/邮件
- 在仪表盘事件流里显示

---

## 🛠 常用运维命令

```bash
# 看最近状态(从本地 SQLite 读,不调 Orbio)
python -m bagbot.cli status

# 跑一次巡检然后退出(用于排错 / cron)
python -m bagbot.cli once

# 强制跑一次 6 个 MCP 工具自检(会消耗余额)
python -m bagbot.cli probe

# macOS launchd 服务管理
launchctl list | grep bagbot
launchctl unload ~/Library/LaunchAgents/com.keyneszeng.bagbot.plist
tail -f ~/Library/Logs/bagbot.out.log

# Linux systemd 服务管理
systemctl --user status bagbot
journalctl --user -u bagbot -f
```

---

## 🔒 安全建议

- **ORBIO_MCP_TOKEN 极其敏感**:拿到它就能 claim 你钱包里 $ORBIO 派生的所有 key。
  - **绝对不要** commit 到 git(`.gitignore` 已经屏蔽 `.env`)
  - 生产环境建议用系统 keychain / KMS,而不是明文 `.env`
- **本仓库的 `.env.example` 里所有 secret 都是空白的**——填你的真实值
- **不要在公共 WiFi / 不熟悉的 VPS 上跑**——Orbio 0 提醒,你的 key 可能被扫描
- **建议把持币钱包和"日常操作钱包"分开**:BagBot 只需要 1,000+ $ORBIO 的"操作钱包",不要把主仓放进来

---

## ❓ 常见问题

### Q1. 我的 token 在哪里看?

Orbio 目前**没有公开的 token 管理页面**。你第一次在 Claude Code 里 `/mcp` 认证后,token 存在你的系统 keychain。具体位置:
- macOS: Keychain Access 搜 "orbio"
- Linux: `~/.config/` 找 MCP 配置文件

### Q2. `probe` 跑完后,我多了一个 key,会一直占着额度吗?

不会。`probe` 内部**最后一步会 `delete_key`**,把 key 干掉,未用余额回到你的 Orbio 账户。

### Q3. 我能在多台机器上跑 BagBot 吗?

可以,但要**用同一个持币钱包**。每台机器的 BagBot 会**独立** claim 自己的 key(它们用的是同一个未领取余额池)。建议:
- **生产机器**:跑 BagBot,挂上完整通知
- **备份机器**:只跑 `python -m bagbot.cli once` 定时巡检,不出手

### Q4. 燃烧速度是怎么算的?

BagBot 每次巡检都读 `orbio_get_key_status`,记下当时的 `spend_usd` 和 `ts`。两次采样之差除以时间,就是 USD/h。**默认 $20/h 触发 rotate**。

### Q5. 我不想要中文,能切英文吗?

`.env` 里改 `LANGUAGE=en`,所有通知和仪表盘都切英文。

---

## 🪐 进阶用法

### 用自己的策略

`src/bagbot/policy.py` 的 `decide()` 是纯函数,你可以继承重写:

```python
from bagbot.policy import decide, Snapshot, PolicyConfig, Action

def my_decide(snap: Snapshot, cfg: PolicyConfig):
    # 例如:周末不出手,等周一再 claim
    import datetime
    if datetime.datetime.now().weekday() >= 5 and snap.action == Action.CLAIM:
        return Action.NOTHING, "weekend: skip"
    return decide(snap, cfg)
```

把这段写到 `my_policy.py`,然后改 `daemon.py` 里 `self.policy_decide = my_decide`。

### 把 BagBot 嵌进你自己的 Agent

```python
from bagbot.orbio_mcp import OrbioMCPClient

async with OrbioMCPClient(url, token) as mcp:
    bal = await mcp.get_balance()
    key = await mcp.claim_key(cap_usd=50.0)
    # 把 key.secret 配进你的 LLM SDK
    import openai
    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key.secret,
    )
    # 用!消费完了 key.secret 没用了,BagBot daemon 会在后台给你 rotate
```

---

## 🆘 出问题怎么办

1. **先看日志**: `tail -f data/bagbot.log`
2. **看仪表盘事件流**: http://127.0.0.1:8765
3. **跑 `python -m bagbot.cli status`**:从本地 SQLite 看最近 key / 事件
4. **到 GitHub 提 issue**: [github.com/keyneszeng/bagbot/issues](https://github.com/keyneszeng/bagbot/issues)
5. **联系作者**: X [@keyneszeng](https://x.com/keyneszeng)

---

## 📜 License

MIT。Fork it,改它,做你自己的版本。
