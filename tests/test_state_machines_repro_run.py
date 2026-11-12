"""Phase 1 repro tests for docs/plans/implicit-state-machines-2026-11-11.md.

Rows B1, B2, B4, B6, B7. They began as xfail(strict) tests asserting the
CORRECT behaviour; Phase 3 fixed each one, so they are plain tests now.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from reasoner.application.services import idempotency
from reasoner.application.services.run_metering import (
    RunContext,
    metered,
    release_unstarted,
)
from reasoner.core.aggregates.pipeline import PipelineAggregate
from reasoner.core.events.domain_events import EventType, make_event
from reasoner.infrastructure.redis.run_state import CANCELLED_SET, RunStateManager

pytestmark = pytest.mark.unit


# ── B1: PipelineAggregate status ────────────────────────────────────────────

def _agg(*events: tuple[EventType, dict]) -> PipelineAggregate:
    agg = PipelineAggregate("p1")
    for version, (etype, fields) in enumerate(events, start=1):
        agg.apply(make_event(etype, "p1", version, **fields))
    return agg


_STARTED = (EventType.PIPELINE_STARTED, {"problem": "q", "preset": "x", "method": "m"})
_COMPLETED = (EventType.PIPELINE_COMPLETED, {"solution": {"a": 1}, "total_tokens": {"total": 1}})
_FAILED = (EventType.PIPELINE_FAILED, {"error": "late", "phase_at_failure": "p"})


def test_b1_failed_after_completed_keeps_completed():
    agg = _agg(_STARTED, _COMPLETED, _FAILED)
    assert agg.state_data.status == "completed"


def test_b1_started_after_terminal_does_not_reset():
    agg = _agg(_STARTED, _COMPLETED, _STARTED)
    assert agg.state_data.status == "completed"


_CANCELLED = (EventType.PIPELINE_CANCELLED, {"reason": "stopped by user", "phase_at_cancel": "p"})


def test_b1_cancelled_is_terminal_and_absorbing():
    agg = _agg(_STARTED, _CANCELLED, _COMPLETED, _FAILED, _STARTED)
    assert agg.state_data.status == "cancelled"
    assert agg.is_cancelled and agg.can_resume() is False


def test_b1_illegal_event_is_counted_not_raised(monkeypatch):
    from reasoner.core.aggregates import pipeline as agg_mod

    seen: list[tuple] = []
    monkeypatch.setattr(agg_mod, "count_illegal_transition", lambda *a: seen.append(a))
    _agg(_STARTED, _COMPLETED, _FAILED)
    assert seen == [("pipeline_run", "completed", "failed")]


@pytest.mark.parametrize("prefix", ["cancelled: stopped by user", "client_disconnected: gone"])
def test_b1_old_failed_prefix_replays_as_cancelled(prefix):
    # Streams written before PIPELINE_CANCELLED existed stored a stop as a failure.
    agg = _agg(_STARTED, (EventType.PIPELINE_FAILED, {"error": prefix, "phase_at_failure": "p"}))
    assert agg.state_data.status == "cancelled"
    assert agg.state_data.errors == []


def test_b1_terminal_run_is_not_resumable():
    # Guard that holds: a terminal aggregate reports can_resume() False.
    assert _agg(_STARTED, _COMPLETED).can_resume() is False
    assert _agg(_STARTED, _FAILED).can_resume() is False


def test_b1_running_without_terminal_is_resumable_by_design():
    # DEBATABLE: the plan calls this a bug, but resuming a hard-killed run
    # (no terminal event) is what can_resume() exists for. RunStream.disconnected()
    # now writes a terminal event for the soft-kill cases, so only a hard kill
    # reaches this state. Documented, not asserted as a defect.
    assert _agg(_STARTED).can_resume() is True


# ── B2: outcome vocabulary ──────────────────────────────────────────────────

def _run_stream(monkeypatch):
    from reasoner.api.execution import sse_observer

    persisted: list = []

    async def fake_persist(event):
        persisted.append(event)
        return True

    monkeypatch.setattr(sse_observer, "_persist_event", fake_persist)
    sent: list[dict] = []

    async def emit(payload):
        sent.append(payload)

    stream = sse_observer.RunStream("r1", emit, lambda _p: None)
    return stream, persisted, sent


async def test_b2_disconnect_is_not_stored_as_failure(monkeypatch):
    stream, persisted, _ = _run_stream(monkeypatch)
    await stream.disconnected(None)
    assert persisted, "disconnect must still write a terminal event"
    assert persisted[0].event_type == EventType.PIPELINE_CANCELLED


async def test_b2_failed_still_ends_with_done_by_design(monkeypatch):
    # Pinned, not a defect: `done` is the terminator the agent/MCP routes and the
    # TypeScript SDK's summarise() fold a run from (it reads `done.errors`), and
    # the SSE frame contract is additive-only. The `error` frame before it
    # carries the typed code.
    stream, _, sent = _run_stream(monkeypatch)
    await stream.failed(RuntimeError("boom"), None)
    terminal = [p["type"] for p in sent if p["type"] in ("error", "done")]
    assert terminal == ["error", "done"]


from tests.test_phase_quality_gate import _execute, harness  # noqa: E402, F401  (fixture)


async def test_b2_user_cancel_persists_a_terminal_event(harness, monkeypatch):  # noqa: F811
    import asyncio

    import reasoner.api.execution.pipeline as mod

    cancel = asyncio.Event()

    async def add(run_id, user_id=None):
        return cancel

    monkeypatch.setattr(mod._run_store, "add", add)
    harness.block_phase = asyncio.Event()  # the phase never finishes by itself
    task = asyncio.ensure_future(_execute(harness))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if harness.phase_runs:
            break
    assert harness.phase_runs, "the phase never started"
    cancel.set()  # what /api/stop does
    events, outcome = await asyncio.wait_for(task, timeout=5)

    assert outcome.status == "cancelled"
    assert any(e["type"] == "cancelled" for e in events)
    terminal = [
        e for e in harness.persisted
        if e.event_type in (
            EventType.PIPELINE_FAILED, EventType.PIPELINE_COMPLETED, EventType.PIPELINE_CANCELLED
        )
    ]
    assert [e.event_type for e in terminal] == [EventType.PIPELINE_CANCELLED]
    agg = PipelineAggregate("quality-gate-test")
    for e in harness.persisted:
        agg.apply(e)
    assert agg.is_cancelled and agg.can_resume() is False


# ── B4: metered() settlement ────────────────────────────────────────────────

class _Sink:
    def __init__(self) -> None:
        self.true_ups: list[dict] = []

    async def true_up(self, **kw) -> None:
        self.true_ups.append(kw)

    async def settle(self, **kw) -> None:
        self.true_ups.append(kw)

    async def record_unsettled(self, **kw) -> None: ...

    async def release_quota_slot(self, *, user_id: str, claimed_at=None) -> None: ...


def _frame(**event) -> str:
    return "data: " + json.dumps(event)


@pytest.fixture
def released(monkeypatch):
    calls: list[str | None] = []

    async def fake(claim):
        calls.append(claim)

    monkeypatch.setattr("reasoner.application.services.idempotency.release_run", fake)
    return calls


async def _drain(gen) -> None:
    async for _ in gen:
        pass


async def test_b4_spent_run_without_done_keeps_claim(released):
    async def stream():
        yield _frame(type="phase_complete", total_cost_usd=0.05)
        # client hangs up / run dies before the terminal done frame

    ctx = RunContext(preset="x", reference_id="r", run_claim="u:cid")
    await _drain(metered(stream(), ctx, _Sink()))
    assert released == []


async def test_b4_free_run_without_done_releases_claim(released):
    # Guard that holds: nothing spent, so the id may be retried.
    async def stream():
        yield _frame(type="start")

    ctx = RunContext(preset="x", reference_id="r", run_claim="u:cid")
    await _drain(metered(stream(), ctx, _Sink()))
    assert released == ["u:cid"]


async def test_b4_claim_released_at_most_once(released):
    # DEBATABLE reachability: needs metered() entered after release_unstarted.
    ctx = RunContext(preset="x", reference_id="r", run_claim="u:cid", started=__import__("asyncio").Event())
    await release_unstarted(_Sink(), ctx)

    async def stream():
        yield _frame(type="start")

    await _drain(metered(stream(), ctx, _Sink()))
    assert len(released) == 1


# ── B6: idempotency claim ───────────────────────────────────────────────────

class _FakeManager:
    """SET NX / compare-and-delete / compare-and-mark-done, as RunStateManager does against Redis."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    async def is_authoritative(self) -> bool:
        return True

    async def try_register(self, key: str, token: str = "1") -> bool:
        if key in self.keys:
            return False
        self.keys[key] = token
        return True

    async def release(self, key: str, token: str) -> None:
        if self.keys.get(key) == token:
            del self.keys[key]

    async def complete(self, key: str, token: str) -> None:
        if self.keys.get(key) == token:
            self.keys[key] = "done"

    async def claim_finished(self, key: str) -> bool:
        return self.keys.get(key) == "done"


@pytest.fixture
def manager(monkeypatch):
    m = _FakeManager()
    monkeypatch.setattr("reasoner.infrastructure.redis.run_state._run_state_manager", m)
    return m


async def test_b6_live_run_retry_is_refused_as_in_progress(manager):
    await idempotency.register_run("cid", owner_key="u")
    with pytest.raises(idempotency.RunAlreadyInProgressError) as info:
        await idempotency.register_run("cid", owner_key="u")
    assert not isinstance(info.value, idempotency.RunAlreadyFinishedError)


async def test_b6_finished_run_retry_is_refused_as_finished(manager):
    # Deliberately still a 409 (a completed run keeps its claim); only the
    # message changes, so the caller is not told a dead run is "in progress".
    from fastapi import HTTPException

    from reasoner.api.idempotency_http import register_run_or_error

    claim = await idempotency.register_run("cid", owner_key="u")
    await idempotency.complete_run(claim)
    with pytest.raises(idempotency.RunAlreadyFinishedError):
        await idempotency.register_run("cid", owner_key="u")
    with pytest.raises(HTTPException) as info:
        await register_run_or_error("cid", owner_key="u")
    assert info.value.status_code == 409 and "already finished" in info.value.detail


async def test_b6_finished_claim_cannot_be_released_by_its_old_holder(manager):
    claim = await idempotency.register_run("cid", owner_key="u")
    await idempotency.complete_run(claim)
    await idempotency.release_run(claim)
    with pytest.raises(idempotency.RunAlreadyFinishedError):
        await idempotency.register_run("cid", owner_key="u")


def test_b6_in_memory_store_release_is_owner_checked():
    from reasoner.infrastructure.redis.in_memory import RunStateStore

    store = RunStateStore()
    assert store.try_register("k", token="a")
    store.release("k", "b")
    assert not store.try_register("k", token="c")
    store.release("k", "a")
    assert store.try_register("k", token="c")


async def test_b6_stale_release_does_not_free_new_holders_claim(manager):
    stale = await idempotency.register_run("cid", owner_key="u")      # run A
    await idempotency.release_run(stale)                              # A fails
    await idempotency.register_run("cid", owner_key="u")              # run B retries
    await idempotency.release_run(stale)                              # A's late/double release
    with pytest.raises(idempotency.RunAlreadyInProgressError):        # B must still hold it
        await idempotency.register_run("cid", owner_key="u")


# ── B7: run registry and cancel ─────────────────────────────────────────────

class _FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}
        self.kv: dict[str, str] = {}

    async def set(self, k, v, **_kw):
        self.kv[k] = v
        return True

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    async def sadd(self, k, v):
        self.sets.setdefault(k, set()).add(v)

    async def srem(self, k, v):
        self.sets.get(k, set()).discard(v)

    async def sismember(self, k, v):
        return v in self.sets.get(k, set())

    async def smembers(self, k):
        return set(self.sets.get(k, set()))

    async def expire(self, *_a):
        return True


@pytest.fixture
def rsm():
    m = RunStateManager()
    m._redis = _FakeRedis()
    return m


async def test_b7_late_cancel_does_not_cancel_reused_run_id(rsm):
    await rsm.add("r1")
    await rsm.remove("r1")           # run ended
    await rsm.request_cancel("r1")   # late /api/stop
    await rsm.add("r1")              # same id reused (resume reuses the pipeline id)
    assert await rsm.is_cancelled("r1") is False


async def test_b7_remove_clears_a_flag_set_before_it(rsm):
    # remove() SREMs the cancel flag; add() clears one that landed after it.
    await rsm.add("r1")
    await rsm.request_cancel("r1")
    assert "r1" in rsm._redis.sets[CANCELLED_SET]
    await rsm.remove("r1")
    assert "r1" not in rsm._redis.sets.get(CANCELLED_SET, set())


async def test_b7_cancel_requested_polls_is_cancelled(monkeypatch):
    import asyncio

    from reasoner.api.execution import pipeline as p

    store = SimpleNamespace(is_cancelled=AsyncMock(return_value=True))
    monkeypatch.setattr(p, "_run_store", store)
    monkeypatch.setattr(p, "_CANCEL_POLL_SECONDS", 0.01)
    await asyncio.wait_for(p._cancel_requested("r1", asyncio.Event()), timeout=2)
    store.is_cancelled.assert_awaited()
