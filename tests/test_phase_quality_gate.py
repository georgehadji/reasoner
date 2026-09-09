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

    calls = SimpleNamespace(phase_runs=0, reset=[], monitor=None)

    async def phase_fn(state, services):
        calls.phase_runs += 1
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
            return SimpleNamespace(_get_method_from_preset=lambda: "multi-perspective")

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
    monkeypatch.setattr(mod, "reset_phase_state", lambda name, state: calls.reset.append(name))
    monkeypatch.setattr(mod, "check_run_allowed", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "apply_spend_limits", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "_save_history_entry", lambda entry: None)

    async def _tier(user_id):
        return SimpleNamespace(value="free")

    async def _persist(evt):
        return None

    monkeypatch.setattr(mod, "resolve_user_tier", _tier)
    monkeypatch.setattr(mod, "_persist_event", _persist)
    monkeypatch.setattr(
        mod, "get_pipeline_ownership_repo",
        lambda: SimpleNamespace(set_owner=lambda *a, **kw: asyncio.sleep(0)),
    )

    monkeypatch.setattr("reasoner.application.flows.factory.WorkflowFactory", _Factory)
    monkeypatch.setattr(
        "reasoner.application.flows.services.PipelineWorkflowServices",
        lambda pipeline: SimpleNamespace(pipeline=pipeline),
    )
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
    await PipelineExecutionService().execute_run(
        command, MagicMock(), sse_emit, user_id=None, initial_state=PipelineState(
            problem="Does the quality gate run?", preset_name="multi-perspective-budget"
        ),
    )
    return events


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
