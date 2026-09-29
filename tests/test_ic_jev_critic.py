"""Iterative Critique with jev as the first critic.

JEV_MODE=active: jev scores the answer on the critic's four dimensions; if all
clear ACCEPT_SCORE the round is ACCEPT and the LLM critic never runs. Anything
else -- a dimension below the bar, a failure, a timeout, an answer too long to
judge whole -- runs the LLM critic exactly as before, because a REVISE round
needs flaws and jev writes none. Offline: jev is a fake DecisionPort and the
LLMs are a fake WorkflowServices that records every call by role.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest

import reasoner.phases.iterative_critique as ic_phases
from reasoner.application.flows import iterative_critique_phases as icp
from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.core.ports.decision_port import DecisionResult, set_decision_port
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState

_PROBLEM = "How should a 12-person clinic reduce appointment no-shows?"
_ANSWER = "Send SMS reminders 48h and 2h before, overbook the two worst slots, charge a small fee."

# Level positions 0..5 stand for 0..10 (x2). 4.0 -> 8.0, exactly ACCEPT_SCORE.
_ALL_STRONG = {"factuality": 4.5, "reasoning": 4.2, "completeness": 4.0, "clarity": 4.8}


def _jev_answers(levels: dict[str, float]) -> dict[str, dict[str, Any]]:
    return {d: {"type": "score", "score": p, "confidence": 0.9} for d, p in levels.items()}


class FakePort:
    def __init__(self, levels=None, exc: BaseException | None = None, delay: float = 0.0):
        self.levels = levels if levels is not None else _ALL_STRONG
        self.exc = exc
        self.delay = delay
        self.calls: list[tuple[Any, dict]] = []

    async def decide(self, state, questions):
        self.calls.append((state, questions))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return DecisionResult(answers=_jev_answers(self.levels),
                              model="typesafe/jev-1.13-20260917", cost_usd=7e-05)


_LLM_CRITIC = json.dumps({
    "scores": {"factuality": 7, "reasoning": 6, "completeness": 5, "clarity": 8},
    "flaws_identified": [{"flaw": "No measure of baseline no-show rate", "severity": "MED"}],
    "verdict": "REVISE",
})


class FakeServices:
    """WorkflowServices with every LLM call recorded by role."""

    def __init__(self, critic_reply: str = _LLM_CRITIC):
        self.critic_reply = critic_reply
        self.roles: list[str] = []

    def log(self, tag, message, state=None):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.roles.append(role)
        if role == "expert_2":  # the critic
            return self.critic_reply, {}
        return json.dumps({"answer": _ANSWER, "revised_answer": _ANSWER + " (revised)"}), {}

    @property
    def critic_calls(self) -> int:
        return self.roles.count("expert_2")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.fixture
def jev(monkeypatch):
    def _set(mode: str, port: FakePort | None) -> FakePort | None:
        monkeypatch.setattr(settings, "JEV_MODE", mode)
        set_decision_port(port)
        return port

    return _set


def _state() -> PipelineState:
    return PipelineState(problem=_PROBLEM)


# ── run_critic_phase ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_off_is_the_llm_critic_exactly(jev):
    port = jev("off", FakePort())
    svc = FakeServices()
    rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)
    assert (rnd.verdict, svc.critic_calls, port.calls) == ("REVISE", 1, [])


@pytest.mark.asyncio
async def test_active_jev_accept_skips_the_llm_critic(jev):
    port = jev("active", FakePort(_ALL_STRONG))
    svc = FakeServices()
    rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)

    assert rnd.verdict == "ACCEPT"
    assert svc.critic_calls == 0
    assert rnd.critic_model == "typesafe/jev-1.13-20260917"
    assert rnd.flaws_identified == []
    assert rnd.critic_score.completeness == pytest.approx(8.0)  # level 4.0 -> 8.0
    state_sent, questions = port.calls[0]
    assert state_sent == {"problem": _PROBLEM, "answer": _ANSWER}
    assert questions is ic_phases.JEV_CRITIC_QUESTIONS


@pytest.mark.asyncio
@pytest.mark.parametrize("dim", ["factuality", "reasoning", "completeness", "clarity"])
async def test_active_one_dimension_below_the_bar_runs_the_llm_critic(jev, dim):
    jev("active", FakePort({**_ALL_STRONG, dim: 3.9}))  # 7.8 < 8
    svc = FakeServices()
    rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)
    assert svc.critic_calls == 1
    assert rnd.verdict == "REVISE"
    assert rnd.flaws_identified  # the flaws the next revision needs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "port",
    [
        FakePort(exc=RuntimeError("jev down")),
        FakePort(levels={"factuality": 4.5}),  # partial answers -> KeyError
    ],
)
async def test_active_jev_failure_falls_back_to_the_llm_critic(jev, port):
    jev("active", port)
    svc = FakeServices()
    rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)
    assert (rnd.verdict, svc.critic_calls) == ("REVISE", 1)


@pytest.mark.asyncio
async def test_active_jev_timeout_falls_back_to_the_llm_critic(jev, monkeypatch):
    monkeypatch.setattr(icp, "JEV_CRITIC_TIMEOUT_SECONDS", 0.01)
    jev("active", FakePort(delay=1.0))
    svc = FakeServices()
    assert (await icp.run_critic_phase(_state(), svc, _ANSWER, 1)).verdict == "REVISE"
    assert svc.critic_calls == 1


@pytest.mark.asyncio
async def test_active_an_answer_too_long_to_judge_whole_is_not_sent(jev, monkeypatch):
    monkeypatch.setattr(icp, "JEV_MAX_STATE_CHARS", 50)
    port = jev("active", FakePort(_ALL_STRONG))
    svc = FakeServices()
    rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)
    assert port.calls == []  # skipped, not truncated
    assert (rnd.verdict, svc.critic_calls) == ("REVISE", 1)


@pytest.mark.asyncio
async def test_shadow_runs_both_and_uses_the_llm_round(jev, caplog):
    port = jev("shadow", FakePort(_ALL_STRONG))  # jev would accept
    svc = FakeServices()
    with caplog.at_level(logging.INFO, logger=icp.__name__):
        rnd = await icp.run_critic_phase(_state(), svc, _ANSWER, 1)
    assert (rnd.verdict, svc.critic_calls, len(port.calls)) == ("REVISE", 1, 1)
    record = _logged(caplog)
    assert (record["source"], record["jev_accepts"], record["agree_accept"]) == ("llm", True, False)


@pytest.mark.asyncio
async def test_the_log_carries_a_hash_not_the_text(jev, caplog):
    jev("active", FakePort(_ALL_STRONG))
    with caplog.at_level(logging.INFO, logger=icp.__name__):
        await icp.run_critic_phase(_state(), FakeServices(), _ANSWER, 1)
    record = _logged(caplog)
    assert record["source"] == "jev" and record["jev_accepts"] is True
    assert "no-shows" not in caplog.text and "SMS" not in caplog.text


def _logged(caplog) -> dict[str, Any]:
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("jev_ic {"))
    return json.loads(line.removeprefix("jev_ic "))


# ── One rule, both critics ────────────────────────────────────────────


def test_the_llm_critic_prompt_renders_the_same_accept_score():
    prompt = ic_phases.critic_evaluation_prompt(_state(), _ANSWER, 1)
    assert f"If all scores >= {ic_phases.ACCEPT_SCORE}: verdict=ACCEPT" in prompt


def test_the_accept_level_is_labelled_as_what_accept_score_means():
    """Level position 4 is 8 on 0-10: its label must describe ACCEPT."""
    levels = ic_phases.JEV_CRITIC_QUESTIONS["factuality"]["criteria"]
    assert levels[ic_phases.ACCEPT_SCORE // 2].startswith(f"{ic_phases.ACCEPT_SCORE} strong")


# ── The loop ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_jev_accept_ends_the_loop_after_one_round(jev):
    jev("active", FakePort(_ALL_STRONG))
    state, svc = _state(), FakeServices()
    await IterativeCritiqueFlow()._run_debate_loop(state, svc)
    assert len(state.adversarial_rounds) == 1
    assert state.adversarial_convergence_reason == "critic_accepted"
    assert svc.critic_calls == 0
    assert svc.roles == ["expert_1"]  # the generator, once


@pytest.mark.asyncio
async def test_a_revise_round_still_feeds_its_flaws_to_the_next_revision(jev):
    """Round 1 below the bar (LLM flaws), round 2 accepted by jev."""
    port = FakePort({**_ALL_STRONG, "completeness": 3.0})
    jev("active", port)
    state, svc = _state(), FakeServices()

    original = port.decide

    async def decide_then_improve(s, q):
        out = await original(s, q)
        port.levels = _ALL_STRONG  # the revision fixed completeness
        return out

    port.decide = decide_then_improve
    await IterativeCritiqueFlow()._run_debate_loop(state, svc)

    assert [r.verdict for r in state.adversarial_rounds] == ["REVISE", "ACCEPT"]
    assert svc.critic_calls == 1  # only on the REVISE round
    assert state.adversarial_rounds[0].flaws_identified  # what round 2 revised against
