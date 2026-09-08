"""BagBot 端到端闭环 demo —— 不需要真实 Orbio token。

用一个 MockTransport 模拟 Orbio MCP 的 6 个工具响应，按场景推进：
  tick 1: 没有key、余额$10  → 应该 CLAIM
  tick 2: key已用85%、有钱   → 应该 TOPUP
  tick 3: key已老(>168h)     → 应该 ROTATE
  tick 4: key耗尽+没钱topup  → 应该 ROTATE
  tick 5: 没key、余额$1      → 应该 ALERT

每个 tick 打印：余额 / 决策 / 执行 / SQLite 记账 / 中文通知。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# 让脚本能直接跑（用仓库的 src/）
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from bagbot.config import Settings
from bagbot.daemon import BagBot
from bagbot.orbio_mcp import OrbioMCPClient
from bagbot.state import KeyRecord


# ── 一个会"随 tick 推进剧情"的 mock MCP server ─────────────────────

class FakeOrbio:
    """按 tick 序号返回不同的 MCP 响应，演示完整闭环。"""

    def __init__(self):
        self.tick = 0
        # 每 tick 的 (get_balance, get_key_status, claim/topup/rotate 的返回)
        self.scenarios = [
            # tick 1: 无 key, 余额 $10 → CLAIM
            dict(
                balance={"earned": 10.0, "claimed": 0.0, "unclaimed": 10.0},
                claim={"key_id": "k_demo_1", "secret": "sk-or-v1-AAA", "headroom": 200.0},
                note="场景1: 无key + 余额$10 → 期望 CLAIM",
            ),
            # tick 2: key 用了 85% (spend=170/headroom=30) → TOPUP
            dict(
                balance={"earned": 10.0, "claimed": 0.0, "unclaimed": 10.0},
                status={"key_id": "k_demo_1", "spend": 170.0, "headroom": 30.0, "remaining": 30.0},
                topup={"key_id": "k_demo_1", "headroom": 200.0, "spend": 170.0},
                note="场景2: key已用85% + 有余额 → 期望 TOPUP",
            ),
            # tick 3: key 已 8 天老 → ROTATE(按年龄)
            dict(
                balance={"earned": 10.0, "claimed": 0.0, "unclaimed": 10.0},
                status={"key_id": "k_demo_1", "spend": 170.0, "headroom": 30.0, "remaining": 30.0},
                rotate={"key_id": "k_demo_2", "secret": "sk-or-v1-BBB", "headroom": 30.0},
                note="场景3: key已老(>168h) → 期望 ROTATE(年龄)",
            ),
            # tick 4: key耗尽 + 余额$0 → ROTATE(没钱topup)
            dict(
                balance={"earned": 0.5, "claimed": 0.5, "unclaimed": 0.0},
                status={"key_id": "k_demo_2", "spend": 30.0, "headroom": 0.0, "remaining": 0.0},
                rotate={"key_id": "k_demo_3", "secret": "sk-or-v1-CCC", "headroom": 0.0},
                note="场景4: key耗尽 + 余额$0 → 期望 ROTATE(没钱)",
            ),
            # tick 5: 无 key + 余额$1 → ALERT
            dict(
                balance={"earned": 1.0, "claimed": 0.0, "unclaimed": 1.0},
                note="场景5: 无key + 余额$1 → 期望 ALERT",
            ),
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        """httpx MockTransport 回调：按请求体里的 tool 名返回对应响应。"""
        try:
            body = json.loads(request.content.decode())
            tool = body.get("params", {}).get("name", "")
            args = body.get("params", {}).get("arguments", {})
        except Exception:
            tool, args = "", {}

        sc = self.scenarios[self.tick] if self.tick < len(self.scenarios) else self.scenarios[-1]

        # 把 tool 名 + 当前 tick 编号记下来用于调试
        payload: dict
        if tool == "orbio_get_balance":
            payload = sc.get("balance", {})
        elif tool == "orbio_claim_key":
            payload = sc.get("claim", {})
        elif tool == "orbio_get_key_status":
            payload = sc.get("status", {})
        elif tool == "orbio_top_up_key":
            payload = sc.get("topup", {})
        elif tool == "orbio_rotate_key":
            payload = sc.get("rotate", {})
        elif tool == "orbio_delete_key":
            payload = {}
        else:
            payload = {}

        # 包装成 MCP "result.structuredContent" 形状
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {"structuredContent": payload},
            },
        )


# ── 一个把通知打到屏幕的 fake notifier ─────────────────────────────

class PrintingNotifier:
    """替真 Notifier：把每条中文通知直接 print 出来，证明闭环。"""

    name = "print"

    def __init__(self, lang="zh-CN"):
        self.lang = lang

    async def notify(self, level, kind, title, summary, payload=None):
        emoji = {"info": "🔵", "warn": "🟡", "error": "🔴", "success": "🟢"}.get(level, "⚪")
        print(f"    {emoji} 通知 [{level}/{kind}] {title}")
        print(f"       {summary}")


# ── 把 MockTransport 注入到 OrbioMCPClient ─────────────────────────

def patched_client(url: str, token: str, fake: FakeOrbio) -> OrbioMCPClient:
    """造一个 OrbioMCPClient，内部 httpx client 用我们的 MockTransport。"""
    c = OrbioMCPClient(url, token)
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler),
        base_url=c.endpoint,
        headers={"Authorization": f"Bearer {token}"},
    )
    # 跳过 async ctx manager 的重新创建
    return c


# ── 主流程 ──────────────────────────────────────────────────────────

async def main():
    print("=" * 64)
    print("  BagBot 端到端闭环 demo（无真实 token，用 mock MCP）")
    print("=" * 64)

    # 临时 SQLite + 临时日志
    fd, db_path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd); os.unlink(db_path)

    # 用 Settings 但覆盖关键字段
    os.environ.setdefault("ORBIO_WALLET", "0xDemoWallet0000...0000")
    os.environ.setdefault("ORBIO_MCP_TOKEN", "demo-token-not-real")
    os.environ.setdefault("ORBIO_MCP_URL", "https://demo.orbio.example/mcp")
    os.environ["STATE_DB_PATH"] = db_path
    os.environ["DASHBOARD_ENABLED"] = "false"
    os.environ["WEBHOOK_ENABLED"] = "false"
    os.environ["FEISHU_ENABLED"] = "false"
    os.environ["WECHAT_ENABLED"] = "false"
    os.environ["EMAIL_ENABLED"] = "false"

    # reload settings 让 env 生效
    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    settings = cfg_module.get_settings()

    # 让 tick 间隔短一点（demo 不等 300s）
    settings.poll_interval_sec = 1

    bot = BagBot(settings)
    await bot.state.init()

    # 替换真 MCP client 和真 notifier
    fake = FakeOrbio()
    bot.mcp = patched_client(settings.orbio_mcp_url, settings.orbio_mcp_token, fake)
    bot.notifier = PrintingNotifier(lang=settings.language)

    # tick 3 需要一个"老"key：我们手动塞一个 8 天前的 key 进 SQLite
    # tick 3 才会走到 age-based rotate
    print("\n▶ 初始化：先塞一个 8 天前的 key 进 SQLite（让 tick 3 能触发 age-rotate）")
    await bot.state.save_key(KeyRecord(
        key_id="k_demo_1", secret="sk-or-v1-OLD",
        headroom_usd=200.0, spend_usd=0.0,
        created_at=time.time() - 8 * 24 * 3600,   # 8 天前
    ))
    # 但 tick 1 我们想演示"无key→CLAIM"，所以先把这条 retire 掉
    await bot.state.retire_key("k_demo_1", "demo setup")
    # tick 1 时 current_key() 应为 None

    for i in range(5):
        fake.tick = i
        sc = fake.scenarios[i] if i < len(fake.scenarios) else fake.scenarios[-1]
        print(f"\n┌── Tick {i+1} ─────────────────────────────────")
        print(f"│ {sc.get('note','')}")
        print(f"│ 模拟余额: {sc.get('balance',{})}")

        # tick 3 需要那个 8 天老 key 还在（之前 retire 了，现在复活）
        if i == 2:
            await bot.state.save_key(KeyRecord(
                key_id="k_demo_1", secret="sk-or-v1-OLD",
                headroom_usd=200.0, spend_usd=0.0,
                created_at=time.time() - 8 * 24 * 3600,
            ))
        # tick 4 用 k_demo_2（上一轮 rotate 出来的）
        if i == 3:
            # 把 k_demo_1 retire，k_demo_2 active
            await bot.state.retire_key("k_demo_1", "rotated by age in tick3")
            await bot.state.save_key(KeyRecord(
                key_id="k_demo_2", secret="sk-or-v1-BBB",
                headroom_usd=30.0, spend_usd=0.0,
                created_at=time.time() - 100,
            ))
        # tick 5: 清掉所有 key，演示 ALERT
        if i == 4:
            await bot.state.retire_key("k_demo_3", "setup for alert demo")
            # current_key() 应返回 None

        try:
            report = await bot.tick()
            print(f"│")
            print(f"│ 决策 action = {report.action.value}")
            print(f"│ 原因 reason = {report.reason}")
            if report.status:
                print(f"│ key 状态: spend=${report.status.spend_usd:.2f} "
                      f"remaining=${report.status.remaining_usd:.2f}")
            cur = await bot.state.current_key()
            print(f"│ 当前 active key: {cur.key_id if cur else '(none)'}")
        except Exception as e:
            print(f"│ ✗ tick 失败: {e}")
        print(f"└────────────────────────────────────────────")

    # 最后看 SQLite 里记了什么
    print("\n" + "=" * 64)
    print("  SQLite 状态快照（demo 结束）")
    print("=" * 64)
    print("\n▶ 最近 5 条事件:")
    events = await bot.state.recent_events(limit=5)
    for e in events:
        print(f"  [{e['level']:5s}] {e['kind']:14s} {e['message'][:60]}")

    print("\n▶ 最近 key 历史:")
    for k in await bot.state.recent_keys(limit=5):
        ret = f"retired({k.retire_reason})" if k.retired_at else "ACTIVE"
        print(f"  {k.key_id:12s} headroom=${k.headroom_usd:.0f}  {ret}")

    print("\n▶ 余额快照:")
    for b in await bot.state.recent_balances(limit=3):
        print(f"  earned=${b['earned_usd']:.2f} unclaimed=${b['unclaimed_usd']:.2f}")

    # 清理
    try: os.unlink(db_path)
    except: pass
    print("\n✅ 端到端闭环 demo 完成 — 无需任何真实凭证。")


if __name__ == "__main__":
    asyncio.run(main())
