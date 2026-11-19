"""The debate stops before a round that will not fit its phase timeout.

"use the iterative critique method to tell me how to land a recruiting job in
Greece" failed with "Phase timeout: Adversarial Debate exceeded 180.0s"
(2026-11-09): up to five generator+critic rounds run back to back, and the
phase timeout cancelled the whole phase, rounds already finished included.
"""

from __future__ import annotations

import json

import pytest

import reasoner.application.flows.iterative_critique as ic_flow
from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.core.ports.decision_port import set_decision_port
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState


def _critic(score: int, flaw: str) -> str:
    return json.dumps({
        "scores": dict.fromkeys(("factuality", "reasoning", "completeness", "clarity"), score),
        "flaws_identified": [{"flaw": flaw, "severity": "HIGH"}],
        "verdict": "REVISE",
        "rationale": "r",
    })


class _SlowServices:
    """Every LLM call advances a fake clock by *seconds_per_call*."""

    def __init__(self, clock, seconds_per_call: float):
        self._clock = clock
        self._step = seconds_per_call
        self._round = 0
        self.calls = 0

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.calls += 1
        self._clock.now += self._step
        if role == "expert_2":
            self._round += 1
            # Rising scores and fresh flaws: never converges on its own.
            return _critic(min(self._round * 2, 8), f"flaw-{self._round}"), {"model": "critic"}
        return json.dumps({"answer": f"answer-{self.calls}"}), {"model": "gen"}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _jev_off(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.mark.asyncio
async def test_slow_rounds_stop_inside_the_budget(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ic_flow, "_clock", clock)
    services = _SlowServices(clock, seconds_per_call=50.0)  # 100s per round
    state = PipelineState(problem="How do I land a recruiting job in Greece?")

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    # 180s phase: a second 100s round would end at 200s, so it never starts.
    assert len(state.adversarial_rounds) == 1
    assert state.adversarial_convergence_reason == "time_budget"
    assert state.adversarial_converged is False
    assert clock.now - 1000.0 < 180.0


@pytest.mark.asyncio
async def test_fast_rounds_are_not_cut_short(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ic_flow, "_clock", clock)
    services = _SlowServices(clock, seconds_per_call=5.0)  # 10s per round
    state = PipelineState(problem="p")

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    assert state.adversarial_convergence_reason != "time_budget"
    assert len(state.adversarial_rounds) >= 2


class _UnevenServices(_SlowServices):
    """Each call advances the clock by the next entry of *seconds*."""

    def __init__(self, clock, seconds: list[float]):
        super().__init__(clock, 0.0)
        self._seconds = list(seconds)

    async def call_llm(self, *a, **k):
        self._step = self._seconds.pop(0) if self._seconds else 1.0
        return await super().call_llm(*a, **k)


@pytest.mark.asyncio
async def test_one_slow_round_sets_the_estimate_not_the_average(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ic_flow, "_clock", clock)
    # round 1: 10s, round 2: 80s -> 90s elapsed of a 162s budget (180s x 0.9).
    # The average (45s) would allow round 3; the slowest round (80s) does not.
    services = _UnevenServices(clock, [5.0, 5.0, 40.0, 40.0])
    state = PipelineState(problem="p")

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    assert len(state.adversarial_rounds) == 2
    assert state.adversarial_convergence_reason == "time_budget"
