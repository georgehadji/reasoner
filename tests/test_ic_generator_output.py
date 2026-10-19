"""IC-2: the generator's whole reply must reach the round, not just its answer string.

run_generator_phase used to return the revised answer only, so `changes_summary`,
`flaw_responses` (AGREE/DISAGREE per flaw) and the serving model were discarded
and synthesis always saw `changes: ""`.
"""
from __future__ import annotations

import json

import pytest

from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.application.flows.iterative_critique_phases import run_generator_phase
from reasoner.core.ports.decision_port import set_decision_port
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases.iterative_critique import synthesis_prompt

_REVISE = json.dumps({
    "scores": {"factuality": 5, "reasoning": 5, "completeness": 5, "clarity": 5},
    "flaws_identified": [{"flaw": "no evidence", "severity": "HIGH", "evidence": "x"}],
    "verdict": "REVISE",
    "rationale": "needs work",
})
_ACCEPT = json.dumps({
    "scores": {"factuality": 9, "reasoning": 9, "completeness": 9, "clarity": 9},
    "flaws_identified": [],
    "verdict": "ACCEPT",
    "rationale": "good",
})
_REVISION = json.dumps({
    "flaw_responses": [
        {"flaw": "no evidence", "stance": "DISAGREE", "response": "the claim is axiomatic"},
    ],
    "revised_answer": "v2 answer",
    "changes_summary": "added the axiom argument",
    "key_claims": ["c1"],
    "confidence": 0.7,
})


class _Services:
    def __init__(self, generator_replies, critic_replies):
        self._gen = list(generator_replies)
        self._critic = list(critic_replies)

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        if role == "expert_2":
            return self._critic.pop(0), {"model": "critic/model-1"}
        return self._gen.pop(0), {"model": "gen/model-1"}


@pytest.fixture(autouse=True)
def _jev_off(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.mark.asyncio
async def test_round_carries_the_generators_full_reply():
    state = PipelineState(problem="Is axiom A needed?")
    services = _Services(
        [json.dumps({"answer": "v1 answer"}), _REVISION], [_REVISE, _ACCEPT]
    )

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    r1, r2 = state.adversarial_rounds
    assert r2.answer == "v2 answer"
    assert r2.changes_summary == "added the axiom argument"
    assert r2.flaw_responses[0]["stance"] == "DISAGREE"
    assert r2.key_claims == ["c1"]
    assert r2.generator_model == "gen/model-1"
    assert r1.critic_model == r2.critic_model == "critic/model-1"
    assert not r2.degraded


@pytest.mark.asyncio
async def test_synthesis_prompt_shows_changes_and_rejected_flaws():
    state = PipelineState(problem="Is axiom A needed?")
    services = _Services(
        [json.dumps({"answer": "v1 answer"}), _REVISION], [_REVISE, _ACCEPT]
    )
    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    prompt = synthesis_prompt(state)

    assert "added the axiom argument" in prompt
    assert "axiomatic" in prompt  # the DISAGREE reply is visible to synthesis


@pytest.mark.asyncio
async def test_malformed_generator_json_keeps_previous_answer_and_marks_degraded():
    state = PipelineState(problem="p")
    services = _Services(["not json at all"], [])

    out = await run_generator_phase(
        state, services, previous_answer="kept", flaws=[{"flaw": "f"}], round_num=2
    )

    assert out.degraded is True
    assert out.answer == "kept"
    assert out.model == "gen/model-1"


@pytest.mark.asyncio
async def test_generator_degraded_round_is_flagged_on_the_round():
    state = PipelineState(problem="p")
    services = _Services(["garbage", "garbage"], [_REVISE, _REVISE])

    await IterativeCritiqueFlow()._run_debate_loop(state, services)

    assert all(r.degraded for r in state.adversarial_rounds)
    assert state.adversarial_convergence_reason == "critic_unavailable"
