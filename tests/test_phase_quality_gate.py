"""The per-phase quality gate has to actually execute.

In `api/execution/pipeline.py` the whole gate — `phase_monitor.evaluate`, the
`phase_quality` frame, `state.quality_history`, hint injection, the
`phase_retry` frame and `reset_phase_state` — sat *after* a `try` whose body
ended in `break` and whose two handlers ended in `break`. Every branch left the
retry loop before reaching it, so the gate had never run once in production.

Line coverage could not see that. The enclosing `for retry_attempt` loop is
exercised on every run, so it reads as covered while the statements inside it
are unreachable. That is why this file exists as a behavioural test and why
`tests/architecture/test_unreachable_after_try.py` exists as a structural one:
neither catches the other's failure.

The test drives `PipelineExecutionService.execute_run` with a single phase whose
quality evaluation fails on the first attempt and passes on the second, and
asserts the consequences a user would see.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from reasoner.application.commands import RunPipelineCommand
from reasoner.application.flows.base import PhaseStep
from reasoner.domain.pipeline_state import PipelineState

# Budget 1 in PHASE_RETRY_BUDGETS, i.e. two attempts: one retry is exactly the
# budget this test needs and the smallest that exercises the branch.
PHASE_NAME = "Perspectives"


@dataclass
class _Quality:
    score: float
    passed: bool
    reason: str
    suggestions: list[str]


class _FakeMonitor:
    """Fails the first attempt, passes the second."""

    def __init__(self, router, preset_name=None):
        self.attempts: list[int] = []

    async def evaluate(self, name, state, attempt: int = 1):
        self.attempts.append(attempt)
        if attempt == 1:
            return _Quality(3.0, False, "too thin", ["add a second perspective"])
        return _Quality(8.0, True, "ok", [])


@pytest.fixture
def harness(monkeypatch):
    """Stub everything around the retry loop, leaving the loop itself real."""
    import reasoner.api.execution.pipeline as mod

    router = MagicMock()
    router.describe.return_value = "test-router"

    calls = SimpleNamespace(
        phase_runs=0, reset=[], monitor=None, persisted=[], preflight_error=None, block_phase=None
    )

    async def phase_fn(state, services):
        calls.phase_runs += 1
        if calls.block_phase is not None:
            await calls.block_phase.wait()
        state.errors.append(f"attempt-{calls.phase_runs}") if False else None

    class _Strategy:
        def get_phases(self, state):
            return [PhaseStep(2.0, PHASE_NAME, phase_fn, lambda s: {"ok": True})]

    class _Factory:
        def get_strategy(self, method):
            return _Strategy()

    class _Orchestrator:
        def __init__(self, *a, **kw):
            pass

        async def preflight(self, req, initial_state=None, user_id=None):
            if calls.preflight_error is not None:
                raise calls.preflight_error
            return SimpleNamespace(
                action="pipeline",
                gate_reasoning=None,
                router=router,
                effective_preset_name="multi-perspective-budget",
                auto_selected_method=None,
                recalled_chunks=None,
                conversation_history=None,
                previous_synthesis=None,
                turn_number=1,
            )

        async def postflight(self, *a, **kw):
            return None

    class _PipelineService:
        def create_pipeline(self, **kw):
            # PipelineWorkflowServices is no longer stubbed: execute_run hands
            # the real one to WorkflowRunner, so the fake pipeline has to carry
            # what that adapter reads off it.
            return SimpleNamespace(
                _get_method_from_preset=lambda: "multi-perspective",
                router=router,
                _log=lambda phase, message, state: None,
            )

    class _RunStore:
        async def add(self, run_id, user_id=None):
            return asyncio.Event()

        async def remove(self, run_id):
            return None

    def _fake_monitor(router_, preset_name=None):
        calls.monitor = _FakeMonitor(router_, preset_name)
        return calls.monitor

    monkeypatch.setattr(mod, "_run_store", _RunStore())
    monkeypatch.setattr(mod, "PipelineOrchestrator", _Orchestrator)
    monkeypatch.setattr(mod, "PipelineService", _PipelineService)
    monkeypatch.setattr(mod, "PhaseMonitor", _fake_monitor)
    monkeypatch.setattr(
        "reasoner.application.flows.runner.reset_phase_state",
        lambda name, state: calls.reset.append(name),
    )
    monkeypatch.setattr(mod, "check_run_allowed", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "apply_spend_limits", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "_save_history_entry", lambda entry: None)

    async def _tier(user_id, **kwargs):
        return SimpleNamespace(value="free")

    async def _persist(evt):
        calls.persisted.append(evt)
        return True

    monkeypatch.setattr(mod, "resolve_user_tier", _tier)
    # Event persistence lives in RunStream now, not in the execution module.
    monkeypatch.setattr("reasoner.api.execution.sse_observer._persist_event", _persist)
    monkeypatch.setattr(
        mod, "get_pipeline_ownership_repo",
        lambda: SimpleNamespace(set_owner=lambda *a, **kw: asyncio.sleep(0)),
    )

    monkeypatch.setattr("reasoner.application.flows.factory.WorkflowFactory", _Factory)
    monkeypatch.setattr("reasoner.core.memory.TaggedMemory", lambda *a, **kw: MagicMock())
    # Layer B appends an "Egress Rewrite" step to every flow when enabled, which
    # would put a second phase through the gate and make these counts depend on a
    # deployment setting rather than on the loop.
    monkeypatch.setattr(
        "reasoner.application.services.egress_policy.resolve_egress_policy",
        lambda **kw: SimpleNamespace(layer_b_enabled=False),
    )

    return calls


async def _run(mod_calls) -> list[dict]:
    events, _state = await _run_returning_state(mod_calls)
    return events


async def _run_returning_state(mod_calls) -> tuple[list[dict], object]:
    events, outcome = await _execute(mod_calls)
    return events, outcome.state


async def _execute(mod_calls) -> tuple[list[dict], object]:
    from reasoner.api.execution.pipeline import PipelineExecutionService

    events: list[dict] = []

    async def sse_emit(payload):
        if isinstance(payload, dict):
            events.append(payload)

    command = RunPipelineCommand(
        command_id="quality-gate-test",
        timestamp=0.0,
        problem="Does the quality gate run?",
        preset="multi-perspective-budget",
    )
    outcome = await PipelineExecutionService().execute_run(
        command, MagicMock(), sse_emit, user_id=None, initial_state=PipelineState(
            problem="Does the quality gate run?", preset_name="multi-perspective-budget"
        ),
    )
    return events, outcome


@pytest.mark.asyncio
async def test_execute_run_returns_the_state_it_built(harness):
    """The streaming path's return value, which nothing asserted until now.

    `execute_run` is annotated `-> PipelineState` and every path returned None:
    four bare `return`s and a fall-through. RunPipelineCommandHandler assigns
    that to `state` and passes it straight to `_completion_payload`, which
    reads `state.phase_tokens`. So every finished web run raised
    AttributeError in the handler *after* the client already had its `done`
    frame -- recording PIPELINE_FAILED instead of PIPELINE_COMPLETED and
    emitting a spurious trailing `error` frame.

    tests/test_completion_event_contract.py drives handler.handle() without
    sse_emit, so it exercises the non-streaming branch and never saw this.
    This test rides the harness above because that is what drives execute_run
    end to end.
    """
    _events, state = await _run_returning_state(harness)

    assert state is not None, "execute_run returned None; the handler cannot complete the run"
    assert isinstance(state, PipelineState)
    assert state.problem == "Does the quality gate run?"


@pytest.mark.asyncio
async def test_failed_quality_check_retries_the_phase(harness):
    """A failing evaluation with budget left must produce a second attempt."""
    events = await _run(harness)

    assert harness.monitor is not None, "phase_monitor.evaluate was never reached"
    assert harness.monitor.attempts == [1, 2], (
        f"expected two evaluations, got {harness.monitor.attempts}"
    )
    assert harness.phase_runs == 2, f"phase ran {harness.phase_runs}x, expected a retry"
    assert harness.reset == [PHASE_NAME], "state was not reset between attempts"

    types = [e.get("type") for e in events]
    assert types.count("phase_quality") == 2, types
    assert "phase_retry" in types, types


@pytest.mark.asyncio
async def test_quality_result_reaches_the_client(harness):
    """The gate's verdict is part of phase_complete, not just an internal score."""
    events = await _run(harness)

    retry = next(e for e in events if e.get("type") == "phase_retry")
    assert retry["attempt"] == 1
    assert retry["max_attempts"] == 2
    assert retry["reason"] == "too thin"

    complete = next(e for e in events if e.get("type") == "phase_complete")
    assert complete["data"]["quality"] == {"score": 8.0, "passed": True}


@pytest.mark.asyncio
async def test_run_gate_resolves_tier_with_the_long_budget_and_no_fallback_memory(harness, monkeypatch):
    """The gate that decides a run the caller already reserved credits for must not
    inherit the request path's 1s cap or its remembered-FREE fallback."""
    import reasoner.api.execution.pipeline as mod
    from reasoner.application.services.spend_limit_service import RUN_TIER_LOOKUP_TIMEOUT_S

    seen = {}

    async def _tier(user_id, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(value="free")

    monkeypatch.setattr(mod, "resolve_user_tier", _tier)
    await _run(harness)

    assert seen == {"timeout": RUN_TIER_LOOKUP_TIMEOUT_S, "use_fallback_cache": False}


@pytest.mark.asyncio
async def test_spend_cap_stops_quality_retries(harness, monkeypatch):
    """BIL-9: the cap was checked only at phase start, so a phase that tripped
    it still ran its quality-gate retries and kept spending."""
    original = _FakeMonitor.evaluate

    async def evaluate(self, name, state, attempt: int = 1):
        state._spend_cap_exceeded = True  # this attempt's calls crossed the cap
        return await original(self, name, state, attempt)

    monkeypatch.setattr(_FakeMonitor, "evaluate", evaluate)
    await _run(harness)

    assert harness.monitor.attempts == [1]
    assert harness.phase_runs == 1, "no retry once the spend cap has tripped"


@pytest.mark.asyncio
async def test_finished_run_is_a_completed_outcome(harness):
    _events, outcome = await _execute(harness)

    assert outcome.status == "completed"
    assert isinstance(outcome.state, PipelineState)


@pytest.mark.asyncio
async def test_preflight_failure_is_a_failed_outcome_with_its_cause(harness):
    """RUN-8: the state is None here, and the handler used to dereference it."""
    harness.preflight_error = ValueError("API key OPENROUTER_API_KEY not set")

    events, outcome = await _execute(harness)

    assert outcome.status == "failed"
    assert outcome.state is None
    assert "ValueError" in (outcome.reason or "")
    assert any(e.get("type") == "error" for e in events)


@pytest.mark.asyncio
async def test_disconnect_leaves_a_terminal_event_in_the_store(harness):
    """RUN-7: CancelledError skipped every terminal write, so the stored run
    stayed `running` for ever and could be resumed as if it were live."""
    from reasoner.core.events.domain_events import EventType

    harness.block_phase = asyncio.Event()  # the phase never finishes by itself
    task = asyncio.ensure_future(_execute(harness))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if harness.phase_runs:
            break
    assert harness.phase_runs, "the phase never started"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    terminal = [
        e for e in harness.persisted
        if e.event_type in (EventType.PIPELINE_FAILED, EventType.PIPELINE_COMPLETED)
    ]
    assert terminal, "no terminal event was persisted on disconnect"
    assert terminal[-1].event_type == EventType.PIPELINE_FAILED
    assert "client_disconnected" in terminal[-1].error
