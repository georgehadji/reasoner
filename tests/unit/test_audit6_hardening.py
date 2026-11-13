"""Audit-6 hardening: retry scope, persist timeout, retention, cache bound,
websocket send timeout/replay ordering, tenant single-build."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from reasoner.core.events.domain_events import EventType, make_event
from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.valkey.memory_cache_adapter import InMemoryCacheAdapter
from reasoner.infrastructure.valkey.memory_state_adapter import InMemoryStateAdapter
from reasoner.infrastructure.websocket import manager as ws_manager
from reasoner.infrastructure.websocket.manager import WebSocketManager, WebSocketMessage


# ── 1. retry scope / persist timeout ─────────────────────────────────
def test_retry_scope_excludes_breaker_and_programming_errors():
    pytest.importorskip("aiocircuitbreaker")  # postgres_store imports it at module level
    from aiocircuitbreaker import CircuitBreakerError

    from reasoner.infrastructure.persistence.postgres_store import _TRANSIENT_DB_ERRORS

    assert not issubclass(CircuitBreakerError, _TRANSIENT_DB_ERRORS)
    assert not issubclass(TypeError, _TRANSIENT_DB_ERRORS)
    assert issubclass(ConnectionResetError, _TRANSIENT_DB_ERRORS)
    assert issubclass(TimeoutError, _TRANSIENT_DB_ERRORS)


@pytest.mark.asyncio
async def test_persist_event_times_out_and_reports_not_stored(monkeypatch):
    from reasoner.api import sse_utils
    from reasoner.infrastructure.persistence import event_store

    async def hang(_events):
        await asyncio.sleep(30)

    monkeypatch.setattr(sse_utils, "_PERSIST_TIMEOUT_S", 0.05)
    monkeypatch.setattr(event_store, "get_event_store", lambda: SimpleNamespace(save_events=hang))
    assert await sse_utils._persist_event(SimpleNamespace()) is False


# ── 2. retention of terminal aggregates ──────────────────────────────
@pytest.mark.asyncio
async def test_prune_deletes_terminal_aggregates_only(tmp_path):
    store = EventStore(tmp_path / "ev.db")
    try:
        for agg in ("done", "cancel", "live"):
            await store.save_events([make_event(
                EventType.PIPELINE_STARTED, aggregate_id=agg, version=1,
                problem="p", preset="x", method="m", options={})])
        await store.save_events([make_event(
            EventType.PIPELINE_COMPLETED, aggregate_id="done", version=2)])
        await store.save_events([make_event(
            EventType.PIPELINE_CANCELLED, aggregate_id="cancel", version=2)])
        # Not old enough yet.
        assert await store.prune_events_before(datetime.now(tz=UTC) - timedelta(days=1)) == 0
        deleted = await store.prune_events_before(datetime.now(tz=UTC) + timedelta(days=1))
        assert deleted == 4
        assert await store.get_events("live")
        assert not await store.get_events("done")
        assert not await store.get_events("cancel")
        assert await store.get_aggregate_state("done") is None
        assert await store.get_aggregate_state("live")
    finally:
        store.close()


# ── 3. bounded in-memory adapters ────────────────────────────────────
@pytest.mark.asyncio
async def test_memory_adapters_stay_bounded():
    cache = InMemoryCacheAdapter()
    await cache.set("expired", 1, ttl=-1)
    for i in range(5100):
        await cache.set(f"k{i}", i)
    assert len(cache._store) <= 5000
    assert await cache.get("expired") is None
    assert await cache.get("k5099") == 5099 and await cache.get("k0") is None

    state = InMemoryStateAdapter()
    for i in range(5100):
        await state.set_ex(f"k{i}", "v", 60)
    assert len(state._store) <= 5000


# ── 4. websocket timeouts and replay ordering ────────────────────────
class _WS:
    def __init__(self, hang=False):
        self.client_state = WebSocketState.CONNECTED
        self.accept = AsyncMock()
        self.sent: list[str] = []
        self.hang = hang

    async def send_text(self, text):
        if self.hang:
            await asyncio.sleep(30)
        self.sent.append(text)

    async def send_json(self, data):
        if self.hang:
            await asyncio.sleep(30)


@pytest.mark.asyncio
async def test_stalled_client_is_disconnected_on_send_timeout(monkeypatch):
    monkeypatch.setattr(ws_manager, "WS_SEND_TIMEOUT_S", 0.05)
    mgr = WebSocketManager()
    await mgr.connect(_WS(hang=True), "slow")
    await mgr.send_to_connection("slow", WebSocketMessage(type="event", data={}))
    await asyncio.sleep(0.05)
    assert mgr.get_connection_count() == 0


def _msg(n):
    return WebSocketMessage(type="event", data={"n": n}, pipeline_id="p")


@pytest.mark.asyncio
async def test_replay_completes_before_live_events():
    mgr = WebSocketManager()
    first = _WS()
    await mgr.connect(first, "c0")
    for i in range(3):
        await mgr.broadcast_to_pipeline("p", _msg(i))
    late = _WS()
    await mgr.connect(late, "c1")
    late.sent.clear()
    sub = asyncio.create_task(mgr.subscribe("c1", "p"))
    await asyncio.sleep(0)  # subscription registered, replay in flight
    live = asyncio.create_task(
        mgr.broadcast_to_pipeline("p", _msg(99)))
    await asyncio.gather(sub, live)
    assert "99" in late.sent[-1]


# ── 5. tenant built once ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_concurrent_first_touch_builds_tenant_once(tmp_path, monkeypatch):
    from reasoner.neuro import server

    builds: list[int] = []

    def fake(*_a, **_k):
        builds.append(threading.get_ident())
        time.sleep(0.05)
        return object()

    monkeypatch.setattr(server, "L1Cache", fake)
    monkeypatch.setattr(server, "L2Index", lambda *a, **k: object())
    monkeypatch.setattr(server, "SessionManager", lambda *a, **k: object())
    monkeypatch.setattr(server, "get_agent_data_dir", lambda cfg, aid: tmp_path / (aid or "default"))  # noqa: E501
    mgr = server.TenantManager(SimpleNamespace(cache=None, data_dir=tmp_path))
    a, b, other = await asyncio.gather(mgr.get("t1"), mgr.get("t1"), mgr.get("t2"))
    assert a is b and a is not other
    assert len(builds) == 2  # t1 once, t2 once
