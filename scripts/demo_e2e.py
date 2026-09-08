"""BagBot 端到端闭环 demo —— 不需要真实 Orbio token。

用一个 MockTransport 模拟 Orbio gateway MCP 的 5 个工具响应（payload
形状与 2026-09-08 生产环境实测一致），按场景推进 5 个 tick：

  tick 1: 没有 key、余额 $10       → CREATE（key 免费，花的是账户余额）
  tick 2: key 存在 + 健康          → NOTHING（gateway 自动扣余额）
  tick 3: key 已老(>168h)          → CREATE（原子轮换，replaced=true）
  tick 4: 余额暴跌（疑似泄露）      → REVOKE
  tick 5: key 没了、余额 $1        → ALERT（该多持点 $ORBIO 了）

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

from bagbot.daemon import BagBot
from bagbot.state import KeyRecord


# ── 会"随 tick 推进剧情"的 mock gateway ────────────────────────────

def _usd(v: float) -> dict:
    return {"usd": v, "microUsd": str(int(v * 1_000_000))}


class FakeOrbio:
    """按 tick 序号返回不同的 MCP 响应，演示完整闭环。"""

    def __init__(self):
        self.tick = 0
        # 每 tick 的服务器状态（gateway 模型：账户级，无 key_id 参数）
        self.scenarios = [
            # tick 1: 无 key + 余额 $10 → CREATE
            {
                "balance": 10.0,
                "hasKey": False, "prefix": None,
                "created_hours_ago": 0.0,
                "create": {"key": "sk-orbio-AAA", "prefix": "sk-orbio-aa1",
                           "baseUrl": "https://api.orbio.so/api/v1",
                           "replaced": False},
                "note": "场景1: 无key + 余额$10 → 期望 CREATE（key 免费）",
            },
            # tick 2: key 健康 1h + 正常消耗（$10→$9，约 $12/h）→ NOTHING
            {
                "balance": 9.0,
                "hasKey": True, "prefix": "sk-orbio-aa1",
                "created_hours_ago": 1.0,
                "note": "场景2: key健康(1h) + 正常消耗$12/h → 期望 NOTHING",
            },
            # tick 3: key 老 8 天 → CREATE（原子轮换）
            {
                "balance": 8.0,
                "hasKey": True, "prefix": "sk-orbio-aa1",
                "created_hours_ago": 8 * 24,
                "create": {"key": "sk-orbio-BBB", "prefix": "sk-orbio-bb2",
                           "baseUrl": "https://api.orbio.so/api/v1",
                           "replaced": True},
                "note": "场景3: key已老(192h > 168h) → 期望 CREATE(replaced=true)",
            },
            # tick 4: 余额暴跌（上一 tick $8 → 本 tick $0.1，瞬间烧穿）→ REVOKE
            {
                "balance": 0.1,
                "hasKey": True, "prefix": "sk-orbio-bb2",
                "created_hours_ago": 0.5,
                "revoke": {"revoked": True},
                "note": "场景4: 余额$9→$0.1 暴跌(疑似泄露) → 期望 REVOKE",
            },
            # tick 5: key 存在 + 余额 $1(< $5) → ALERT（该多持点 $ORBIO）
            {
                "balance": 1.0,
                "hasKey": True, "prefix": "sk-orbio-bb2",
                "created_hours_ago": 0.5,
                "note": "场景5: key健康 + 余额$1(< $5) → 期望 ALERT",
            },
        ]

    def _sc(self):
        return self.scenarios[self.tick] if self.tick < len(self.scenarios) \
            else self.scenarios[-1]

    def _status_payload(self) -> dict:
        sc = self._sc()
        from datetime import datetime, timedelta, timezone
        created = (datetime.now(timezone.utc)
                   - timedelta(hours=sc["created_hours_ago"])).isoformat()
        return {
            "hasKey": sc["hasKey"],
            "prefix": sc["prefix"],
            "createdAt": created if sc["hasKey"] else None,
            "lastUsedAt": None,
            "baseUrl": "https://api.orbio.so/api/v1",
            "legacy": None,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        """httpx MockTransport 回调：按 JSON-RPC tool 名返回响应。"""
        try:
            body = json.loads(request.content.decode())
            tool = body.get("params", {}).get("name", "")
        except Exception:
            tool = ""

        sc = self._sc()
        if tool == "orbio_get_balance":
            payload = {
                "wallets": ["0xDemoWallet…0000"],
                "accrued": _usd(100.0), "purchased": _usd(0.0),
                "spent": _usd(100.0 - sc["balance"]), "claimed": _usd(0.0),
                "balance": _usd(sc["balance"]),
            }
        elif tool == "orbio_get_key_status":
            payload = self._status_payload()
        elif tool == "orbio_create_key":
            payload = sc.get("create", {})
        elif tool == "orbio_revoke_key":
            payload = sc.get("revoke", {})
        elif tool == "orbio_delete_key":
            payload = {"refunded": _usd(0.0), "label": None}
        else:
            payload = {}

        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1,
            "result": {"structuredContent": payload},
        })


# ── 把通知打到屏幕的 fake notifier ──────────────────────────────────

class PrintingNotifier:
    """替真 Notifier：把每条中文通知直接 print 出来，证明闭环。"""

    name = "print"

    def __init__(self, lang="zh-CN"):
        self.lang = lang

    async def notify(self, level, kind, title, summary, payload=None):
        emoji = {"info": "🔵", "warn": "🟡", "error": "🔴",
                 "success": "🟢"}.get(level, "⚪")
        print(f"    {emoji} 通知 [{level}/{kind}] {title}")
        print(f"       {summary}")


# ── 主流程 ──────────────────────────────────────────────────────────

async def main():
    print("=" * 64)
    print("  BagBot 端到端闭环 demo（gateway 模型 · 无真实 token）")
    print("=" * 64)

    # 临时 SQLite（跑完清理）
    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd); os.unlink(db_path)

    # 强制设置 mock env（不能用 setdefault —— 会被仓库 .env 的空值骗过）
    os.environ["ORBIO_WALLET"] = "0xDemoWallet0000...0000"
    os.environ["ORBIO_MCP_TOKEN"] = "demo-token-not-real"
    os.environ["ORBIO_MCP_URL"] = "https://demo.orbio.example/mcp"
    os.environ["STATE_DB_PATH"] = db_path
    os.environ["DASHBOARD_ENABLED"] = "false"
    os.environ["WEBHOOK_ENABLED"] = "false"
    os.environ["FEISHU_ENABLED"] = "false"
    os.environ["WECHAT_ENABLED"] = "false"
    os.environ["EMAIL_ENABLED"] = "false"

    from bagbot import config as cfg_module
    cfg_module.reload_settings()
    settings = cfg_module.get_settings()
    settings.poll_interval_sec = 1

    bot = BagBot(settings)
    await bot.state.init()

    # 注入 mock gateway + fake notifier
    fake = FakeOrbio()
    mcp = bot.require_mcp()
    mcp._client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler),
        base_url=mcp.endpoint,
        headers={"Authorization": f"Bearer {mcp.token}"},
    )
    bot.notifier = PrintingNotifier(lang=settings.language)

    for i in range(5):
        fake.tick = i
        sc = fake.scenarios[i] if i < len(fake.scenarios) else fake.scenarios[-1]
        print(f"\n┌── Tick {i + 1} ─────────────────────────────────")
        print(f"│ {sc.get('note', '')}")
        print(f"│ 模拟服务器: 余额=${sc['balance']:.2f} "
              f"hasKey={sc['hasKey']}")

        # tick 3 需要本地有一个"老"key 记录（8 天前创建）才能触发 age 轮换
        if i == 2:
            await bot.state.save_key(KeyRecord(
                key_id="sk-orbio-aa1", secret="sk-orbio-AAA-old",
                headroom_usd=0.0, spend_usd=0.0,
                created_at=time.time() - 8 * 24 * 3600,
            ))

        if i >= 1:
            # 把上一次采样时间回拨到 300s 前，让 burn rate 按
            # 真实 5-min poll 节奏计算（demo 的真实 tick 间隔是毫秒级）。
            bot._last_balance_ts = time.time() - 300.0
        if i == 4:
            # 剧情：leak 事件已处理完。重置 burn 采样，让 tick 5 独立地
            # 演示"健康 key + 低余额 → ALERT"分支，而不是继续算暴跌速率。
            bot._last_balance_usd = None
            bot._last_balance_ts = 0.0
            await bot.state.save_key(KeyRecord(
                key_id="sk-orbio-bb2", secret="sk-orbio-BBB-new",
                headroom_usd=0.0, spend_usd=0.0,
                created_at=time.time(),
            ))

        try:
            report = await bot.tick()
            print("│")
            print(f"│ 决策 action = {report.action.value}")
            print(f"│ 原因 reason = {report.reason}")
            cur = await bot.state.current_key()
            print(f"│ 本地 active key: {cur.key_id if cur else '(none)'}")
        except Exception as e:
            print(f"│ ✗ tick 失败: {e}")
        print("└────────────────────────────────────────────")

    # 最后看 SQLite 记了什么
    print("\n" + "=" * 64)
    print("  SQLite 状态快照（demo 结束）")
    print("=" * 64)

    print("\n▶ 最近 5 条事件:")
    for e in await bot.state.recent_events(limit=5):
        print(f"  [{e['level']:5s}] {e['kind']:20s} {e['message'][:50]}")

    print("\n▶ key 历史:")
    for k in await bot.state.recent_keys(limit=5):
        ret = f"retired({(k.retire_reason or '')[:40]})" if k.retired_at \
            else "ACTIVE"
        print(f"  {k.key_id:16s} {ret}")

    print("\n▶ 余额快照:")
    for b in await bot.state.recent_balances(limit=3):
        print(f"  accrued=${b['earned_usd']:.2f} "
              f"spendable=${b['unclaimed_usd']:.2f}")

    try:
        os.unlink(db_path)
    except OSError:
        pass
    print("\n✅ 端到端闭环 demo 完成 — 无需任何真实凭证。")


if __name__ == "__main__":
    asyncio.run(main())
