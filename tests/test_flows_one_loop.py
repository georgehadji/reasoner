"""Behaviour that moved when `WorkflowStrategy.execute()` was deleted.

Each test here covers one thing that used to run on the CLI and not on the web,
or the other way round, because two drivers executed two different phase lists.
The shape is guarded separately in
`tests/architecture/test_one_phase_loop.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

# Imported for its side effect, before any test patches resolve_egress_policy.
# resolve_phases() imports this module lazily, so without this the first test
# that enables Layer B would import it while the patch is live, freezing the
# fake into its `from ... import resolve_egress_policy` binding for the rest of
# the session -- monkeypatch only reverts the module it patched.
from reasoner.application.flows import egress_rewrite_phase  # noqa: F401
from reasoner.application.flows.base import PhaseStep
from reasoner.application.flows.delphi_phases import run_delphi_dissent_phase
from reasoner.application.flows.jury import JuryFlow
from reasoner.application.flows.runner import WorkflowRunner, resolve_phases
from reasoner.application.flows.writing_phases import run_writing_source_retrieval_phase
from reasoner.domain.pipeline_state import PipelineState


class _Services:
    """Minimal WorkflowServices double. `router` is unused by the code under test."""

    router: Any = None

    def __init__(self, llm_raises: bool = False):
        self.llm_calls: list[str] = []
        self.logs: list[tuple[str, str]] = []
        self.phases_run: list[str] = []
        self.fail_phase: str | None = None
        self._llm_raises = llm_raises

    def log(self, phase: str, message: str, state: PipelineState) -> None:
        self.logs.append((phase, message))

    async def call_llm(self, role, system_prompt, user_prompt, state, phase_key=None, **kwargs):
        self.llm_calls.append(role)
        if self._llm_raises:
            raise RuntimeError("no network in tests")
        return "{}", {"model": "fake"}

    async def run_phase(self, step: PhaseStep, state: PipelineState, **kwargs) -> bool:
        self.phases_run.append(step.name)
        return step.name != self.fail_phase


@pytest.fixture(autouse=True)
def _layer_b_off(monkeypatch):
    """Pin the egress policy; `resolve_phases` reads it and tests must not."""
    import reasoner.application.services.egress_policy as policy

    monkeypatch.setattr(
        policy, "resolve_egress_policy", lambda *a, **k: type("P", (), {"layer_b_enabled": False})()
    )


@pytest.mark.asyncio
async def test_delphi_dissent_skips_when_converged():
    """The skip lived in DelphiFlow.execute(), so the web paid for it every run."""
    state = PipelineState(problem="q")
    state.delphi_state["converged"] = True
    services = _Services()

    await run_delphi_dissent_phase(state, services)

    assert services.llm_calls == []
    assert "dissent" not in state.delphi_state


@pytest.mark.asyncio
async def test_delphi_dissent_runs_when_not_converged():
    state = PipelineState(problem="q")
    state.delphi_state["converged"] = False
    services = _Services()

    await run_delphi_dissent_phase(state, services)

    assert len(services.llm_calls) == 1
    assert state.delphi_state["dissent"] == {}


@pytest.mark.asyncio
async def test_writing_augmentation_runs_once_in_the_phase(monkeypatch):
    """WritingFlow.execute() ran augmentation, so the web never did it at all."""
    import reasoner.application.flows.augmentation as augmentation

    calls = []

    async def _fake_augmentation(state, call_llm, log):
        calls.append(state)
        state.writing_state["pre_research_insights"] = "done"

    monkeypatch.setattr(augmentation, "run_augmentation", _fake_augmentation)

    state = PipelineState(problem="q")
    services = _Services(llm_raises=True)

    await run_writing_source_retrieval_phase(state, services)
    assert len(calls) == 1

    # A quality-gate retry of this phase must not pay for augmentation twice.
    await run_writing_source_retrieval_phase(state, services)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_jury_critical_phase_stops_the_run():
    """JuryFlow.execute() ignored step.critical; the SSE driver honoured it."""
    services = _Services()
    services.fail_phase = "Critic Pool"
    runner = WorkflowRunner(services)

    await runner.run(JuryFlow(), PipelineState(problem="q"))

    assert services.phases_run == ["Evidence Search", "Generation Pool", "Critic Pool"]


class _RecordingObserver:
    """Records hook order. A real one writes SSE frames; both need the order."""

    def __init__(self):
        self.calls: list[str] = []

    async def on_phase_start(self, step, state):
        self.calls.append(f"start:{step.name}")

    async def on_phase_quality(self, step, state, result, attempt):
        self.calls.append(f"quality:{step.name}:{attempt}:{result.passed}")

    async def on_phase_retry(self, step, state, result, attempt, max_attempts):
        self.calls.append(f"retry:{step.name}:{attempt}/{max_attempts}")

    async def on_phase_error(self, step, state, exc, message, fatal):
        self.calls.append(f"error:{step.name}:{type(exc).__name__}:fatal={fatal}")

    async def on_phase_complete(self, step, state, duration, result):
        self.calls.append(f"complete:{step.name}")


@pytest.mark.asyncio
async def test_observer_sees_phase_hooks_in_order(monkeypatch):
    """The SSE driver's frames come from these hooks, so their order is the contract."""
    from reasoner.quality.criteria import PhaseQualityResult

    async def _ok_phase(state, services, **kwargs):
        state.errors.append("noted but survivable")

    services = _Services()
    observer = _RecordingObserver()
    runner = WorkflowRunner(services, observer=observer)
    monkeypatch.setattr(
        runner.monitor,
        "evaluate",
        lambda name, state, attempt=1: _async(PhaseQualityResult(passed=True, score=9.0, reason="ok")),
    )

    step = PhaseStep(2, "Perspectives", _ok_phase, lambda s: {})
    assert await runner.run_phase(step, PipelineState(problem="q")) is True

    assert observer.calls == [
        "start:Perspectives",
        "quality:Perspectives:1:True",
        "complete:Perspectives",
    ]


@pytest.mark.asyncio
async def test_observer_sees_the_exception_that_failed_a_phase():
    """on_phase_error carries the exception: the SSE error frame needs its code."""

    async def _boom(state, services, **kwargs):
        raise ValueError("bad json")

    services = _Services()
    observer = _RecordingObserver()
    runner = WorkflowRunner(services, observer=observer)

    step = PhaseStep(3, "Critique & Pruning", _boom, lambda s: {}, critical=True)
    assert await runner.run_phase(step, PipelineState(problem="q")) is False

    assert observer.calls == [
        "start:Critique & Pruning",
        "error:Critique & Pruning:ValueError:fatal=True",
    ]


def _async(value):
    async def _run():
        return value

    return _run()


def test_fatality_comes_only_from_phasestep_critical():
    """The SSE driver OR'd a hard-coded name set into step.critical.

    `_LEGACY_CRITICAL` in api/phase_executor.py made Perspectives, Opening
    Statements, Generation Pool and Deep Research fatal on the web and
    non-fatal on the CLI, and named five more phases no strategy produces.
    The four live ones are now critical=True where they are declared.
    """
    from reasoner.api import phase_executor
    from reasoner.application.flows.debate import DebateFlow
    from reasoner.application.flows.multi_perspective import MultiPerspectiveFlow
    from reasoner.application.flows.research import ResearchFlow

    assert not hasattr(phase_executor, "_LEGACY_CRITICAL")
    assert not hasattr(phase_executor, "get_critical_phases")

    state = PipelineState(problem="q")
    expected = {
        MultiPerspectiveFlow: "Perspectives",
        DebateFlow: "Opening Statements",
        ResearchFlow: "Deep Research",
        JuryFlow: "Generation Pool",
    }
    for flow_cls, phase_name in expected.items():
        steps = {s.name: s.critical for s in flow_cls().get_phases(state)}
        assert steps[phase_name] is True, f"{flow_cls.__name__}: {phase_name} not critical"


def test_resolve_phases_appends_egress_rewrite_for_every_driver(monkeypatch):
    """This step was appended by the SSE driver alone, so CLI runs never got it."""
    import reasoner.application.services.egress_policy as policy

    monkeypatch.setattr(
        policy, "resolve_egress_policy", lambda *a, **k: type("P", (), {"layer_b_enabled": True})()
    )

    state = PipelineState(problem="q")
    base = JuryFlow().get_phases(state)
    resolved = resolve_phases(JuryFlow(), state)

    assert [s.name for s in resolved] == [s.name for s in base] + ["Egress Rewrite"]
    assert resolved[-1].num == base[-1].num + 0.5
