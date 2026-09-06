"""State store round-trip tests."""

import os
import tempfile
import time

import pytest

from bagbot.state import StateStore, KeyRecord


@pytest.fixture
async def store():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.unlink(path)
    s = StateStore(path)
    await s.init()
    yield s
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_save_and_retrieve_current_key(store: StateStore):
    rec = KeyRecord(
        key_id="k_1", secret="sk-or-v1-xxx", headroom_usd=200.0,
        spend_usd=0.0, created_at=time.time(),
    )
    await store.save_key(rec)

    cur = await store.current_key()
    assert cur is not None
    assert cur.key_id == "k_1"
    assert cur.secret == "sk-or-v1-xxx"
    assert cur.headroom_usd == 200.0


@pytest.mark.asyncio
async def test_retire_key_excludes_from_current(store: StateStore):
    a = KeyRecord(key_id="k_a", secret="s", headroom_usd=200.0,
                  spend_usd=0.0, created_at=time.time() - 10)
    b = KeyRecord(key_id="k_b", secret="s", headroom_usd=200.0,
                  spend_usd=0.0, created_at=time.time())
    await store.save_key(a)
    await store.save_key(b)
    await store.retire_key("k_b", "test reason")

    cur = await store.current_key()
    assert cur is not None
    assert cur.key_id == "k_a"


@pytest.mark.asyncio
async def test_balance_snapshots(store: StateStore):
    for i in range(5):
        await store.record_balance(10 + i, i, 10)
    snaps = await store.recent_balances(limit=3)
    assert len(snaps) == 3
    # most-recent first
    assert snaps[0]["earned_usd"] == 14


@pytest.mark.asyncio
async def test_event_logging_with_payload(store: StateStore):
    await store.log_event("info", "key_claimed", "claimed", {"x": 1})
    events = await store.recent_events(limit=5)
    assert len(events) == 1
    assert events[0]["kind"] == "key_claimed"
    assert events[0]["payload"] == {"x": 1}


@pytest.mark.asyncio
async def test_recent_keys_returns_in_descending_order(store: StateStore):
    for i in range(3):
        await store.save_key(KeyRecord(
            key_id=f"k_{i}", secret="s", headroom_usd=200.0,
            spend_usd=0.0, created_at=time.time() + i,
        ))
    keys = await store.recent_keys(limit=10)
    assert [k.key_id for k in keys] == ["k_2", "k_1", "k_0"]


@pytest.mark.asyncio
async def test_retired_keys_still_in_recent(store: StateStore):
    """Retired keys should still be visible in history, just not in current()."""
    a = KeyRecord(key_id="k_a", secret="s", headroom_usd=200.0,
                  spend_usd=0.0, created_at=time.time() - 10)
    b = KeyRecord(key_id="k_b", secret="s", headroom_usd=200.0,
                  spend_usd=0.0, created_at=time.time())
    await store.save_key(a)
    await store.save_key(b)
    await store.retire_key("k_b", "test")

    keys = await store.recent_keys(limit=10)
    assert len(keys) == 2
    assert {k.key_id for k in keys} == {"k_a", "k_b"}
