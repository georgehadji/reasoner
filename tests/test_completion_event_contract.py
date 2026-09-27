"""PIPELINE_COMPLETED contract tests (T5 orchestration defect hunt).

Both emitters of ``EventType.PIPELINE_COMPLETED`` must agree on the payload
shape that ``PipelineAggregate._apply_pipeline_completed`` and the SSE/telemetry
consumers already assume:

  * ``solution`` is ``{"core_solution": <str>}`` — the synthesis TEXT, never the
    ``FinalSolution`` container. ``ResumePipelineCommandHandler`` hands this
    straight back to a caller as ``previous_synthesis``.
  * ``total_tokens["total"]`` is the real token count. ``state.phase_tokens``
    values carry ``{"input": N, "output": M}`` and no ``"total"`` key (written
    by ``infrastructure/llm/executor.py`` and ``subagents/base.py``), so the
    count has to be derived, not looked up.

The LLM is faked at the ``ProviderRouter.call`` transport boundary — the same
harness ``tests/test_e2e_budget_presets_mock.py`` uses — so the orchestration
under test runs exactly as in production and no network call is made.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from reasoner.application.commands import RunPipelineCommand
from reasoner.application.handlers.handlers import RunPipelineCommandHandler
from reasoner.application.services.preset_service import PresetService
from reasoner.core.events.domain_events import EventType
from reasoner.domain.pipeline_state import PipelineState

_PRESET = "multi-perspective-budget"
_PROBLEM = "What is the capital of France and why is it historically significant?"

_RICH_JSON: dict[str, Any] = {
    "task_type": "factual",
    "language": "English",
    "core_solution": (
        "Paris is the capital of France. It has been the political, economic and "
        "cultural heart of the country for over a thousand years."
    ),
    "critical_insights": ["Paris became the capital under the Capetian dynasty."],
    "action_blueprint": [
        {"step": "1", "action": "Establish Paris as the capital.",
         "time_horizon": "immediate", "go_criteria": "confirmed", "fallback": "re-check"},
    ],
    "open_questions": ["How did the role evolve in the 20th century?"],
    "claim_labels": {"Paris is the capital": "verified"},
    "meta_audit": {
        "most_dangerous_assumption": "Political and cultural significance overlap.",
        "dominant_bias": "Eurocentric framing",
        "remaining_uncertainty": "low",
        "assumption_failure_impact": "limited",
        "non_obvious_insight": "Centrality shaped French unification.",
    },
    "sources": [], "layout_hints": {}, "evidence": {},
    "constructive": "Paris anchors French governance.",
    "destructive": "Centralisation created regional inequality.",
    "systemic": "Paris is a hub in European networks.",
    "minimalist": "Paris is the capital.",
    # `scores` and `stress_tests` were empty here for as long as the quality gate
    # was unreachable on both paths. They are not decoration: with the runner on,
    # `quality/criteria.py` fails "Critique & Pruning" on an empty `scores` and
    # "Stress Testing" on empty `stress_tests`, the phase exhausts its retry
    # budget, and a run that used to synthesise over a hollow critique now stops.
    # A fake transport standing in for a competent model has to return output a
    # competent model would return.
    "scores": [
        {
            "perspective": name,
            "logical_consistency": 8.0,
            "evidence_support": 7.5,
            "failure_resilience": 7.0,
            "feasibility": 8.5,
            "bias_flags": [],
            "steel_man": f"The strongest form of the {name} reading.",
        }
        for name in ("constructive", "destructive", "systemic", "minimalist")
    ],
    "stress_tests": [
        {"scenario": "optimal", "survival_rate": 0.9,
         "failure_mode": "none material", "recovery_path": "n/a"},
        {"scenario": "adversarial", "survival_rate": 0.6,
         "failure_mode": "regional devolution weakens the centre",
         "recovery_path": "treat the claim as historical, not structural"},
    ],
}
_JSON_BLOB = "```json\n" + json.dumps(_RICH_JSON) + "\n```"


async def _fake_call(self, role: str, system_prompt: str, user_prompt: str, **kwargs: Any):
    # Key names match what LLMExecutor reads off ProviderRouter.call metadata
    # (infrastructure/llm/executor.py: metadata.get("input_tokens"/"output_tokens")).
    return _JSON_BLOB, {
        "model": "mock-model",
        "input_tokens": 10,
        "output_tokens": 20,
    }


class _RecordingEventStore:
    """Minimal event-store double: records what the handler tries to persist."""

    def __init__(self) -> None:
        self.saved: list[Any] = []

    async def save_events(self, events: list[Any]) -> None:
        self.saved.extend(events)


@pytest.fixture
def mock_router_call():
    with patch("reasoner.infrastructure.llm.router.ProviderRouter.call", _fake_call):
        yield


@pytest.fixture
def mock_subagents_off():
    with patch("reasoner.pipeline.USE_PHASE_SUBAGENTS", {
        "enhancement": False, "decomposition": False, "critique": False,
        "synthesis": False, "search": False,
    }):
        yield


async def _run_handler(store: _RecordingEventStore):
    _, router = PresetService().build_router(_PRESET)
    handler = RunPipelineCommandHandler(llm_router=router, event_store=store)
    command = RunPipelineCommand(
        command_id=str(uuid.uuid4()),
        timestamp=time.time(),
        problem=_PROBLEM,
        preset=_PRESET,
        method=None,
        top_k=2,
        source_type="general",
        domain=None,
        parallel=True,
    )
    return await handler.handle(command)


def _completed(store: _RecordingEventStore):
    events = [e for e in store.saved if e.event_type == EventType.PIPELINE_COMPLETED]
    assert len(events) == 1, f"expected exactly one completion event, got {len(events)}"
    return events[0]


class TestCompletionEventContract:
    """Proof-of-defect + boundary coverage for the persisted completion event."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_solution_carries_synthesis_text_not_the_container(
        self, mock_router_call, mock_subagents_off
    ):
        """PROOF OF DEFECT: solution['core_solution'] was the FinalSolution object."""
        store = _RecordingEventStore()
        aggregate = await _run_handler(store)
        state = aggregate.pipeline_state
        assert state.final_solution is not None

        event = _completed(store)
        recorded = event.solution["core_solution"]
        assert isinstance(recorded, str), (
            f"solution['core_solution'] must be the synthesis text, got {type(recorded).__name__}"
        )
        assert recorded == state.final_solution.core_solution

        # And the aggregate — the substrate ResumePipelineCommandHandler reads —
        # must therefore expose a plain string too.
        assert isinstance(aggregate.state_data.synthesis.get("core_solution"), str)

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_total_tokens_reflect_actual_usage(
        self, mock_router_call, mock_subagents_off
    ):
        """PROOF OF DEFECT: total_tokens was read off a field PipelineMeta lacks.

        NOTE: this non-SSE path currently leaves ``phase_tokens`` empty (D2 —
        the WorkflowRunner bypass means ``_current_phase_key`` is never set), so
        the expected total is 0 today and becomes non-zero once D2 is fixed.
        Either way the event must AGREE with the state, and must not read a
        field that does not exist. ``test_token_sum_boundary_*`` proves the
        arithmetic on a seeded state.
        """
        store = _RecordingEventStore()
        aggregate = await _run_handler(store)
        state = aggregate.pipeline_state

        expected = sum(
            t.get("input", 0) + t.get("output", 0)
            for t in state.phase_tokens.values()
        )
        event = _completed(store)
        assert event.total_tokens.get("total") == expected
        assert aggregate.state_data.total_tokens.get("total") == expected

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_duration_is_measured_not_zero(
        self, mock_router_call, mock_subagents_off
    ):
        """PROOF OF DEFECT: total_duration_seconds was read off a missing field."""
        store = _RecordingEventStore()
        await _run_handler(store)
        event = _completed(store)
        assert event.total_duration_seconds > 0.0

    # ── Boundary cases ────────────────────────────────────────────────

    def test_token_sum_boundary_no_phases(self):
        """BOUNDARY: a state that never called an LLM totals zero, not a crash."""
        from reasoner.application.handlers.handlers import _completion_payload

        payload = _completion_payload(PipelineState(problem="x"), started_at=time.monotonic())
        assert payload["total_tokens"] == {"total": 0}
        assert payload["solution"] == {"core_solution": ""}

    def test_solution_boundary_no_final_solution(self):
        """BOUNDARY: a pipeline that produced no synthesis records "" — a str."""
        from reasoner.application.handlers.handlers import _completion_payload

        state = PipelineState(problem="x")
        state.phase_tokens["Phase 2: Perspectives"] = {"input": 7, "output": 3}
        payload = _completion_payload(state, started_at=time.monotonic())
        assert payload["solution"]["core_solution"] == ""
        assert payload["total_tokens"] == {"total": 10}

    def test_token_sum_boundary_malformed_phase_entry(self):
        """BOUNDARY: a partially-written phase entry must not raise."""
        from reasoner.application.handlers.handlers import _completion_payload

        state = PipelineState(problem="x")
        state.phase_tokens["a"] = {"input": 5}          # runner's skip-shape, no output
        state.phase_tokens["b"] = {"output": 4}
        payload = _completion_payload(state, started_at=time.monotonic())
        assert payload["total_tokens"] == {"total": 9}


class TestPipelineRunCompletionEvent:
    """The second emitter — ReasonerPipeline.run's own bus event."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_bus_event_total_tokens_nonzero(
        self, mock_router_call, mock_subagents_off
    ):
        """PROOF OF DEFECT: summed a "total" key that phase_tokens never carries."""
        from reasoner.application.event_bus.bus import EventBus
        from reasoner.pipeline import ReasonerPipeline

        seen: list[Any] = []
        real_publish = EventBus.publish

        async def _spy(self, event):
            if event.event_type == EventType.PIPELINE_COMPLETED:
                seen.append(event)
            return await real_publish(self, event)

        with patch.object(EventBus, "publish", _spy):
            _, router = PresetService().build_router(_PRESET)
            pipeline = ReasonerPipeline(
                router=router, preset_name=_PRESET, top_k=2,
                parallel_perspectives=True, verbose=False, source_type="general",
            )
            state = await pipeline.run(_PROBLEM)

        # As above: 0 today because of D2, non-zero once the runner is wired.
        # The contract is that the event agrees with the state.
        expected = sum(
            t.get("input", 0) + t.get("output", 0)
            for t in state.phase_tokens.values()
        )
        assert seen, "ReasonerPipeline.run published no PIPELINE_COMPLETED event"
        assert seen[-1].total_tokens.get("total") == expected


class TestWorkflowRunnerWiring:
    """D2 — the WorkflowRunner on the non-SSE path.

    ``ReasonerPipeline.run`` used to build the runner over a runner-LESS
    ``PipelineWorkflowServices`` and bind the runner-aware one to an unused
    local, so ``runner.run(strategy, state)`` handed the strategy services whose
    ``run_phase`` took the bare ``await step.fn(...)`` fallback. Result: no
    retries, no per-phase timeout, no quality gate, no PHASE_* events, and no
    ``_current_phase_key`` — which is what ``LLMExecutor._accumulate_tokens``
    keys ``phase_tokens`` off, so per-phase token attribution was empty.

    This was xfail until the four event members ``WorkflowRunner`` constructs
    existed: ``PhaseStarted.phase_number``, ``PhaseFailed.is_fatal``,
    ``EventType.PHASE_QUALITY_CHECKED`` and ``EventType.PHASE_RETRIED``. Without
    them the first phase raised TypeError. They exist now, so the test asserts
    the wiring instead of documenting its absence.
    See docs/reports/defect-hunt-2026-09-01/T5-orchestration.md.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_runner_executes_phases(self, mock_router_call, mock_subagents_off, monkeypatch):
        from reasoner.core.settings import settings as _s

        monkeypatch.setattr(_s, "WORKFLOW_RUNNER_ENABLED", True)
        from reasoner.application.flows.runner import WorkflowRunner
        from reasoner.pipeline import ReasonerPipeline

        entered: list[str] = []
        real_run_phase = WorkflowRunner.run_phase

        async def _spy(self, step, state, **kwargs):
            entered.append(step.name)
            return await real_run_phase(self, step, state, **kwargs)

        with patch.object(WorkflowRunner, "run_phase", _spy):
            _, router = PresetService().build_router(_PRESET)
            pipeline = ReasonerPipeline(
                router=router, preset_name=_PRESET, verbose=False, source_type="general",
            )
            state = await pipeline.run(_PROBLEM)

        assert entered, "WorkflowRunner.run_phase was never called"
        assert state.phase_tokens, "no per-phase token attribution was recorded"


class TestWorkflowRunnerFlag:
    """WORKFLOW_RUNNER_ENABLED gates the D2 wiring above rather than applying
    it outright, because switching it on turns on a retry/timeout/quality
    layer that has never executed, for every CLI and headless run at once.
    These prove the FLAG actually controls the wiring, not that the wired
    runner works end to end -- TestRunnerBothWays covers that.

    WorkflowRunner.run is stubbed so these never reach run_phase. That is a
    deliberate scope boundary: this class asks "did pipeline.py rebind the
    services object", not "does the runner's phase execution work".
    """

    @pytest.mark.skipif(
        "WORKFLOW_RUNNER_ENABLED" in os.environ,
        reason="asserts the built-in default; an env override is a deliberate choice",
    )
    @pytest.mark.asyncio
    async def test_enabled_by_default(self):
        """Pinned so a revert to the bypassed path is a visible diff, not drift.

        This asserted ``is False`` while the four event members WorkflowRunner
        constructs were missing, so the first phase raised TypeError. They
        exist, TestRunnerBothWays covers both settings, and the default flipped
        on 2026-09-09.
        """
        from reasoner.core.settings import settings

        assert settings.WORKFLOW_RUNNER_ENABLED is True

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_flag_off_leaves_the_dead_local_pattern(
        self, mock_router_call, mock_subagents_off, monkeypatch
    ):
        """No-regression anchor: proves the CURRENT (buggy) behaviour this
        flag preserved by default until 2026-09-09. The default is on now, so
        the off case has to be asked for explicitly."""
        from reasoner.application.flows.runner import WorkflowRunner
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "WORKFLOW_RUNNER_ENABLED", False)

        captured: dict = {}

        async def _spy(self, strategy, state, config=None):
            captured["services_runner"] = self.services._runner
            return state

        monkeypatch.setattr(WorkflowRunner, "run", _spy)

        store = _RecordingEventStore()
        await _run_handler(store)

        assert "services_runner" in captured, "WorkflowRunner.run was never called"
        assert captured["services_runner"] is None

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_flag_on_wires_the_runner_into_its_own_services(
        self, mock_router_call, mock_subagents_off, monkeypatch
    ):
        """The behaviour this PR adds: with the flag on, the services object
        the runner hands to the strategy is one built WITH that runner, so
        PipelineWorkflowServices.run_phase delegates instead of taking its
        bare `await step.fn(...)` fallback."""
        from reasoner.application.flows.runner import WorkflowRunner
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "WORKFLOW_RUNNER_ENABLED", True)

        captured: dict = {}

        async def _spy(self, strategy, state, config=None):
            captured["runner"] = self
            captured["services_runner"] = self.services._runner
            return state

        monkeypatch.setattr(WorkflowRunner, "run", _spy)

        store = _RecordingEventStore()
        await _run_handler(store)

        assert "services_runner" in captured, "WorkflowRunner.run was never called"
        assert captured["services_runner"] is captured["runner"]


class _RecordingBus:
    """Captures what WorkflowRunner publishes, without touching the real bus."""

    def __init__(self) -> None:
        self.published: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.published.append(event)


class TestRunnerBothWays:
    """The diff the flag's own comment asks for, as a test rather than a ritual.

    ``core/settings.py`` says WORKFLOW_RUNNER_ENABLED may be flipped only after
    diffing a full preset run both ways. A manual diff nobody repeats is not a
    guard, so the comparison runs here: the same preset, the same faked
    transport, once with the runner and once without.

    What must match is the answer. What must differ is the machinery — with the
    runner on, phases emit PHASE_* events and ``_current_phase_key`` is set, so
    per-phase token attribution exists. Off, both are empty, which is exactly
    the defect the flag gates.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    @pytest.mark.parametrize("runner_enabled", [False, True], ids=["off", "on"])
    async def test_same_answer_either_way(
        self, mock_router_call, mock_subagents_off, monkeypatch, runner_enabled
    ):
        from reasoner.core.settings import settings as _s
        from reasoner.pipeline import ReasonerPipeline

        monkeypatch.setattr(_s, "WORKFLOW_RUNNER_ENABLED", runner_enabled)
        bus = _RecordingBus()
        monkeypatch.setattr(
            "reasoner.application.flows.runner.get_event_bus", lambda: bus
        )

        _, router = PresetService().build_router(_PRESET)
        pipeline = ReasonerPipeline(
            router=router, preset_name=_PRESET, verbose=False, source_type="general",
        )
        state = await pipeline.run(_PROBLEM)

        # The contract that must hold identically on both paths.
        assert state.final_solution is not None, (
            f"no synthesis. errors={state.errors} "
            f"quality={state.quality_history} phases={list(state.phase_durations)}"
        )
        assert len(state.final_solution.core_solution) > 10

        published = [e.event_type for e in bus.published]
        if runner_enabled:
            assert EventType.PHASE_STARTED in published, published
            assert EventType.PHASE_COMPLETED in published, published
            assert EventType.PHASE_QUALITY_CHECKED in published, published
            assert state.phase_tokens, "runner on: per-phase tokens must be attributed"
        else:
            assert published == [], (
                "runner off: PipelineWorkflowServices.run_phase takes its bare "
                f"fallback, so nothing should reach the runner's bus; got {published}"
            )


class TestNoRegression:
    """The handler still produces a usable state and a well-formed event stream."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_run_still_completes_with_a_synthesis(
        self, mock_router_call, mock_subagents_off
    ):
        store = _RecordingEventStore()
        aggregate = await _run_handler(store)
        state = aggregate.pipeline_state

        assert state.final_solution is not None
        assert len(state.final_solution.core_solution) > 10
        assert aggregate.state_data.status == "completed"

        types = [e.event_type for e in store.saved]
        assert types == [EventType.PIPELINE_STARTED, EventType.PIPELINE_COMPLETED]
        assert EventType.PIPELINE_FAILED not in types
