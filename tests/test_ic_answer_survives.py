"""The debated answer must survive to the final synthesis.

Live run, 2026-11-10 (iterative-critique-budget, "most profitable apps for
politicians, Greek elections May 2027"): the generator and critic ran under the
roles expert_1/expert_2, which have no PHASE_TOKEN_BUDGETS entry, so both got
the 1536-token default while the budgets written for them (iterative_generate,
iterative_critique) were never read. Every revision -- flaw responses first,
then the complete revised answer -- was cut off, the truncation retry at 3072
was cut off too, the JSON had no revised_answer, two degraded rounds ended the
debate as "critic_unavailable", and the synthesis wrote commentary on the
critic's objections in place of the proposal: the final answer named no app.
"""
from __future__ import annotations

import json

import pytest

from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.core.constants_limits import get_token_budget
from reasoner.core.ports.decision_port import set_decision_port
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases.iterative_critique import SYNTHESIS_SYSTEM, generator_revision_prompt

_REVISE = json.dumps({
    "scores": {"factuality": 5, "reasoning": 5, "completeness": 5, "clarity": 5},
    "flaws_identified": [{"flaw": "no evidence", "severity": "HIGH", "evidence": "x"}],
    "verdict": "REVISE",
})
_ACCEPT = json.dumps({
    "scores": {"factuality": 9, "reasoning": 9, "completeness": 9, "clarity": 9},
    "flaws_identified": [],
    "verdict": "ACCEPT",
})


class _Services:
    def __init__(self):
        self.max_tokens: dict[str, list[int | None]] = {}
        self._critic = [_REVISE, _ACCEPT]

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.max_tokens.setdefault(role, []).append(kwargs.get("max_tokens"))
        if role == "expert_2":
            return self._critic.pop(0), {"model": "critic/m"}
        return json.dumps({"answer": "v", "revised_answer": "v2"}), {"model": "gen/m"}


@pytest.fixture(autouse=True)
def _jev_off(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.mark.asyncio
async def test_generator_and_critic_get_their_own_token_budgets():
    services = _Services()
    await IterativeCritiqueFlow()._run_debate_loop(PipelineState(problem="q"), services)

    assert services.max_tokens["expert_1"] == [get_token_budget("iterative_generate")] * 2
    assert services.max_tokens["expert_2"] == [get_token_budget("iterative_critique")] * 2


def test_budgets_fit_a_full_revision():
    # A revision is per-flaw responses plus the complete answer, often from a
    # reasoning model whose thinking counts against max_tokens. 3072 was
    # observed truncating live.
    assert get_token_budget("iterative_generate") >= 8192
    assert get_token_budget("iterative_critique") >= 3072


def test_revision_asks_for_the_answer_before_the_flaw_responses():
    # Should the reply still run long, the field the round cannot do without
    # is written first.
    prompt = generator_revision_prompt(PipelineState(problem="q"), [], "v1", 2)
    assert prompt.index('"revised_answer"') < prompt.index('"flaw_responses"')


def test_synthesis_must_deliver_the_answer_not_only_its_critique():
    text = SYNTHESIS_SYSTEM.lower()
    assert "core_solution" in text
    assert "best answer" in text
    assert "not a substitute" in text
