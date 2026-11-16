"""Audit A-01: unbilled run-level steps reach the web (SSE) path, not only the CLI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from reasoner.api.execution import pipeline as web
from reasoner.application.flows import synthesis_phase
from reasoner.application.flows.base import PhaseStep
from reasoner.application.flows.runner import WorkflowRunner
from reasoner.application.services.run_steps import drain_fallback_events
from reasoner.domain.models import ClaimLabel
from reasoner.domain.pipeline_state import PipelineState

EVENT = {"role": "synthesis", "intended": "a", "actual": "b", "reason": "429", "ts": 1.0}


class _Services:
    """Stands in for PipelineWorkflowServices: runs the step body, nothing else."""

    router = None

    async def run_phase(self, step, state):
        await step.fn(state, self)
        return True


class _Strategy:
    def __init__(self, fn):
        self._fn = fn

    def get_phases(self, state):
        return [PhaseStep(5, "Synthesis", self._fn, lambda s: {})]


async def test_runner_path_records_reliability_without_pipeline_run(monkeypatch):
    """The SSE driver calls WorkflowRunner.run, never ReasonerPipeline.run."""

    async def fake_synthesize(state, services):
        state.final_solution = SimpleNamespace(
            scope={"as_of": "2026-11-14"},
            claim_labels={"a": ClaimLabel.VERIFIED},
            verification_audit={},
            reliability={},
        )

    monkeypatch.setattr(synthesis_phase, "_synthesize", fake_synthesize)
    state = PipelineState(problem="p")
    runner = WorkflowRunner(_Services(), monitor=object())

    await runner.run(_Strategy(synthesis_phase.run_synthesis_phase), state)

    assert state.final_solution.reliability["level"]


def test_drain_moves_events_once():
    state = PipelineState(problem="p")
    router = SimpleNamespace(_fallback_buffer=[dict(EVENT)])

    drain_fallback_events(state, router)
    drain_fallback_events(state, router)

    assert state.meta.fallback_events == [EVENT]
    assert router._fallback_buffer == []


def test_drain_tolerates_router_without_buffer():
    state = PipelineState(problem="p")
    drain_fallback_events(state, SimpleNamespace())
    assert state.meta.fallback_events == []


@pytest.mark.parametrize("early", [True, False])
async def test_finish_run_saves_fallback_events(monkeypatch, early):
    """What postflight persists is state.meta.fallback_events; it used to be empty."""
    state = PipelineState(problem="p")
    router = SimpleNamespace(_fallback_buffer=[dict(EVENT)])
    if early:
        drain_fallback_events(state, router)
    seen: dict = {}

    async def postflight(st, req, user_id=None, run_id=None):
        seen["events"] = list(st.meta.fallback_events)

    async def done(*_a, **_k):
        return None

    async def no_history(*_a, **_k):
        return None

    monkeypatch.setattr(web, "_record_history", no_history)
    await web._finish_run(
        SimpleNamespace(postflight=postflight),
        SimpleNamespace(),
        state,
        None,
        "run-1",
        0.0,
        SimpleNamespace(done=done),
        router,
    )

    assert seen["events"] == [EVENT]
