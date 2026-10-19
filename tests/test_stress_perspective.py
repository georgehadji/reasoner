"""MP-4: a stress result must say which candidate it stressed.

The prompt used to ask for a bare list of scenarios with no candidate field, so
two top candidates produced three anonymous results and a survival rate could
not be attributed. `recovery_path` was parsed but never requested.
"""
from __future__ import annotations

import json

import pytest

from reasoner.application.flows.perspective_phases import run_stress_test_phase
from reasoner.application.services.serializers import _ser_4
from reasoner.domain.core_types import ScenarioType, SolutionCandidate, StressTestResult
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import PerspectiveRegistry
from reasoner.phases.multi_perspective import stress_test_prompt

_SCENARIOS = ("optimal", "constraint_violation", "adversarial")


class _Services:
    def __init__(self, tests):
        self._tests = tests

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        return json.dumps({"stress_tests": self._tests}), {"model": "m"}


def _state() -> PipelineState:
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    state.top_candidates = [
        SolutionCandidate(
            perspective=PerspectiveRegistry.coerce(p), content=f"{p} plan",
            key_insights=[], model_used="",
        )
        for p in ("constructive", "destructive")
    ]
    return state


@pytest.mark.asyncio
async def test_two_candidates_by_three_scenarios_yield_six_attributed_results():
    tests = [
        {"perspective": p, "scenario": sc, "survival_rate": 0.5,
         "failure_mode": f"{p}/{sc} fails", "recovery_path": "roll back"}
        for p in ("constructive", "destructive") for sc in _SCENARIOS
    ]
    state = _state()

    await run_stress_test_phase(state, _Services(tests))

    assert len(state.stress_results) == 6
    assert {r.perspective for r in state.stress_results} == {"constructive", "destructive"}
    assert all(r.recovery_path == "roll back" for r in state.stress_results)


@pytest.mark.asyncio
async def test_entry_naming_an_unstressed_perspective_is_dropped():
    tests = [
        {"perspective": "systemic", "scenario": "optimal", "survival_rate": 0.9},
        {"perspective": "not-a-perspective", "scenario": "optimal", "survival_rate": 0.9},
        {"perspective": "Constructive", "scenario": "adversarial", "survival_rate": 0.2},
    ]
    state = _state()

    await run_stress_test_phase(state, _Services(tests))

    assert [r.perspective for r in state.stress_results] == ["constructive"]


@pytest.mark.asyncio
async def test_missing_perspective_and_recovery_path_default_to_empty():
    state = _state()

    await run_stress_test_phase(
        state, _Services([{"scenario": "optimal", "survival_rate": 0.8, "failure_mode": "f"}])
    )

    (r,) = state.stress_results
    assert r.perspective == ""
    assert r.recovery_path == ""


def test_prompt_requests_perspective_and_recovery_path():
    prompt = stress_test_prompt(_state())

    assert '"perspective"' in prompt
    assert '"recovery_path"' in prompt
    assert "EACH" in prompt


def test_serializer_exposes_the_perspective():
    state = _state()
    state.stress_results = [
        StressTestResult(
            scenario=ScenarioType.coerce("optimal"),
            survival_rate=0.6, failure_mode="f", recovery_path="r", perspective="destructive",
        )
    ]

    out = _ser_4(state)

    assert out["tests"][0]["perspective"] == "destructive"


def test_old_state_without_perspective_still_constructs():
    r = StressTestResult(scenario=ScenarioType.coerce("optimal"), survival_rate=0.5)
    assert r.perspective == ""
