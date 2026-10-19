"""IC-6: Iterative Critique synthesis speaks the shared synthesis contract.

Its own prompt asked for {core_solution, ...} only, so an IC run came back with
no claim labels, no evidence bundles, no blueprint and no promotion rules, and
a debate that ran out of rounds read as settled.
"""
from __future__ import annotations

import json

import pytest

from reasoner.application.flows.iterative_critique_phases import (
    AdversarialRound,
    run_synthesis_phase,
)
from reasoner.domain.core_types import CriticDimensionScore
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._universal import SYNTHESIS_OUTPUT_FORMAT
from reasoner.phases._universal import SYNTHESIS_SYSTEM as UNIVERSAL_SYSTEM
from reasoner.phases.iterative_critique import SYNTHESIS_SYSTEM, synthesis_prompt, unresolved_flaws

_REPLY = (
    "[SOLUTION]Use read replicas first, then shard.[/SOLUTION]\n"
    "```json\n"
    + json.dumps({
        "critical_insights": ["Replicas buy time"],
        "action_blueprint": [{"step": "1", "action": "Add a replica", "time_horizon": "1w",
                              "go_criteria": "lag < 1s", "fallback": "vertical scale"}],
        "open_questions": ["What is the write ratio?"],
        "claim_labels": {"Replicas cut read load": "VERIFIED"},
        "evidence": [{"claim": "Replicas cut read load", "label": "VERIFIED", "source": "model"}],
        "sources": [],
        "meta_audit": {"most_dangerous_assumption": "reads dominate"},
    })
    + "\n```"
)


class _Services:
    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[tuple[str, str]] = []

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.prompts.append((system_prompt, user_prompt))
        return self.reply, {"model": "m"}


def _score(v=6.0):
    return CriticDimensionScore(factuality=v, reasoning=v, completeness=v, helpfulness=v)


def _state(reason="max_rounds_reached", last_flaws=("no write-ratio data",), degraded_last=False):
    state = PipelineState(problem="How do we scale reads?")
    state.adversarial_rounds = [
        AdversarialRound(round_number=1, answer="a1", critic_score=_score(),
                         flaws_identified=[{"flaw": "old flaw"}], verdict="REVISE"),
        AdversarialRound(round_number=2, answer="a2", critic_score=_score(),
                         flaws_identified=[{"flaw": f} for f in last_flaws], verdict="REVISE"),
    ]
    if degraded_last:
        state.adversarial_rounds.append(
            AdversarialRound(round_number=3, answer="a2", degraded=True,
                             flaws_identified=[{"flaw": "Critic produced malformed JSON"}])
        )
    state.adversarial_converged = reason == "critic_accepted"
    state.adversarial_convergence_reason = reason
    state.adversarial_convergence_round = len(state.adversarial_rounds)
    return state


def test_system_prompt_is_the_universal_one_plus_a_debate_paragraph():
    assert SYNTHESIS_SYSTEM.startswith(UNIVERSAL_SYSTEM)
    assert "DEBATE SYNTHESIS" in SYNTHESIS_SYSTEM


def test_prompt_ends_with_the_shared_output_format():
    prompt = synthesis_prompt(_state())
    assert prompt.endswith(SYNTHESIS_OUTPUT_FORMAT)
    assert "core_solution" not in prompt


@pytest.mark.asyncio
async def test_ic_run_yields_the_full_final_solution_with_promotion_rules():
    state = _state()

    await run_synthesis_phase(state, _Services(_REPLY))

    fs = state.final_solution
    assert fs.core_solution.startswith("Use read replicas first")
    assert fs.action_blueprint and fs.action_blueprint[0]["action"] == "Add a replica"
    assert fs.claim_labels
    (bundle,) = fs.evidence.values()
    assert bundle.label.upper() == "HYPOTHESIS"  # model-sourced VERIFIED is capped


@pytest.mark.asyncio
async def test_unsettled_debate_carries_its_flaws_into_open_questions():
    state = _state(reason="max_rounds_reached")

    await run_synthesis_phase(state, _Services(_REPLY))

    oq = state.final_solution.open_questions
    assert any("no write-ratio data" in q for q in oq)
    assert any("max_rounds_reached" in q for q in oq)
    assert "What is the write ratio?" in oq  # the model's own questions survive


@pytest.mark.asyncio
async def test_accepted_debate_adds_no_unresolved_notes():
    state = _state(reason="critic_accepted")

    await run_synthesis_phase(state, _Services(_REPLY))

    assert state.final_solution.open_questions == ["What is the write ratio?"]


def test_degraded_rounds_do_not_contribute_unresolved_flaws():
    state = _state(degraded_last=True)

    assert unresolved_flaws(state) == ["no write-ratio data"]
