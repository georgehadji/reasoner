"""IC-3: a REJECT verdict starts the approach over; REVISE still patches.

Both used to take the revision path, so a critic saying "this is fundamentally
wrong" got the same answer back with edits.
"""
from __future__ import annotations

import json

import pytest

import reasoner.phases.iterative_critique as ic_phases
from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.application.flows.iterative_critique_phases import NextStep, next_step
from reasoner.core.ports.decision_port import set_decision_port
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState


def _critic(verdict: str, flaw: str = "wrong approach", score: int | None = None) -> str:
    score = score if score is not None else (2 if verdict == "REJECT" else 5)
    return json.dumps({
        "scores": dict.fromkeys(("factuality", "reasoning", "completeness", "clarity"), score),
        "flaws_identified": [{"flaw": flaw, "severity": "HIGH"}],
        "verdict": verdict,
        "rationale": "r",
    })


_ACCEPT = json.dumps({
    "scores": {"factuality": 9, "reasoning": 9, "completeness": 9, "clarity": 9},
    "flaws_identified": [],
    "verdict": "ACCEPT",
    "rationale": "ok",
})


class _Services:
    def __init__(self, critic_replies):
        self._critic = list(critic_replies)
        self.generator_calls: list[tuple[str, str]] = []  # (system, user)
        self._n = 0

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        if role == "expert_2":
            return self._critic.pop(0), {"model": "critic"}
        self._n += 1
        self.generator_calls.append((system_prompt, user_prompt))
        return json.dumps({"answer": "answer-" + str(self._n)}), {"model": "gen"}


@pytest.fixture(autouse=True)
def _jev_off(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("ACCEPT", NextStep.STOP),
        ("REVISE", NextStep.REVISE),
        ("REJECT", NextStep.REGENERATE),
        ("reject", NextStep.REGENERATE),
        ("MAYBE", NextStep.REVISE),
        ("", NextStep.REVISE),
    ],
)
def test_transition_table(verdict, expected):
    assert next_step(verdict) is expected


@pytest.mark.asyncio
async def test_reject_regenerates_with_the_pitfalls_block():
    state = PipelineState(problem="Pick a database")
    services = _Services([_critic("REJECT", "uses a graph store for tabular data"), _ACCEPT])

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    (sys1, _), (sys2, user2) = services.generator_calls
    assert sys2 == ic_phases.GENERATOR_INITIAL_SYSTEM
    assert "REJECTED" in user2
    assert "uses a graph store for tabular data" in user2
    assert "answer-1" in user2  # the rejected approach, to be avoided
    assert "<<<EXTERNAL_CONTENT>>>" in user2
    assert "CRITIC FLAWS" not in user2  # not the revision prompt
    assert sys1 == ic_phases.GENERATOR_INITIAL_SYSTEM


@pytest.mark.asyncio
async def test_revise_still_patches_the_previous_answer():
    state = PipelineState(problem="Pick a database")
    services = _Services([_critic("REVISE", "thin evidence"), _ACCEPT])

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    (_, _), (sys2, user2) = services.generator_calls
    assert sys2 == ic_phases.GENERATOR_REVISION_SYSTEM
    assert "CRITIC FLAWS" in user2
    assert "REJECTED" not in user2


@pytest.mark.asyncio
async def test_regeneration_counts_against_max_rounds():
    from reasoner.application.flows.iterative_critique_phases import MAX_ROUNDS

    state = PipelineState(problem="p")
    # Rising scores and distinct flaws: no plateau or stalemate ends it early.
    replies = [_critic("REJECT", "flaw-" + str(i), score=i * 2) for i in range(MAX_ROUNDS)]
    services = _Services(replies)

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    assert len(state.adversarial_rounds) == MAX_ROUNDS
    assert state.adversarial_convergence_reason == "max_rounds_reached"
