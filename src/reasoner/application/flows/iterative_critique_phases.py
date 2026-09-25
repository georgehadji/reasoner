"""Iterative Critique (LLM Debate) — Phase Logic & Convergence Detection.

Author: DeepSeek TUI — June 2026

Iterative Critique phase logic — adversarial back-and-forth with convergence detection.

Pattern: generator produces answer → critic finds flaws → generator revises → loop until convergence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import reasoner.phases.iterative_critique as ic_phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.core.constants import JEV_CRITIC_TIMEOUT_SECONDS, JEV_MAX_STATE_CHARS
from reasoner.core.ports.decision_port import get_decision_port, jev_mode
from reasoner.domain.core_types import CriticDimensionScore
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
MIN_SCORE_DELTA = 0.5
STALEMATE_FLAW_REPEAT = 3


@dataclass
class AdversarialRound:
    """A single round of the adversarial debate."""
    round_number: int
    generator_model: str = ""
    critic_model: str = ""
    answer: str = ""
    key_claims: list[str] = field(default_factory=list)
    critic_score: CriticDimensionScore | None = None
    flaws_identified: list[dict] = field(default_factory=list)
    verdict: str = ""  # ACCEPT | REVISE | REJECT
    generator_response: str = ""
    revised_answer: str = ""
    changes_summary: str = ""


def check_convergence(rounds: list[AdversarialRound]) -> tuple[bool, str]:
    """Returns (converged, reason)."""
    if not rounds:
        return False, "no_rounds"

    current = rounds[-1]

    if current.verdict == "ACCEPT":
        return True, "critic_accepted"

    if len(rounds) >= MAX_ROUNDS:
        return True, "max_rounds_reached"

    if len(rounds) >= 3:
        scores = [r.critic_score.total if r.critic_score else 0.0 for r in rounds[-3:] if r.critic_score is not None]
        if max(scores) - min(scores) < MIN_SCORE_DELTA:
            return True, "score_converged"

        top_flaws = [r.flaws_identified[0]["flaw"] for r in rounds[-STALEMATE_FLAW_REPEAT:]
                     if r.flaws_identified and r.flaws_identified[0].get("flaw")]
        if len(top_flaws) == STALEMATE_FLAW_REPEAT and len(set(top_flaws)) == 1:
            return True, "stalemate_detected"

    return False, ""


def _safe_float(v: Any) -> float:
    """Defensive float cast — LLM returns nested dicts for scores sometimes."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return 0.0
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_critic_dimensions(scores: Any) -> CriticDimensionScore:
    """Defensive shape cast, in the same spirit as ``_safe_float`` above.

    ``scores`` here is the critic's per-dimension mapping. The same key name in
    the multi-perspective critique (``perspective_phases.run_critique_phase``)
    carries a *list* of per-perspective objects, so a model that returns that
    shape crashed this phase with ``AttributeError: 'list' object has no
    attribute 'get'``. The read at the call site sits outside the try/except
    that exists to turn a malformed critic response into a REVISE round, so the
    whole phase went down instead.
    """
    if not isinstance(scores, dict):
        logger.warning(
            "Critic returned %s for 'scores', expected an object of dimensions "
            "(factuality/reasoning/completeness/clarity); scoring this round 0 "
            "so the verdict drives the retry",
            type(scores).__name__,
        )
        scores = {}
    return CriticDimensionScore(
        factuality=_safe_float(scores.get("factuality", 0)),
        reasoning=_safe_float(scores.get("reasoning", 0)),
        completeness=_safe_float(scores.get("completeness", 0)),
        helpfulness=_safe_float(scores.get("clarity", 0)),
    )


async def run_generator_phase(state: PipelineState, services: WorkflowServices,
                               previous_answer: str = "", flaws: list[dict] | None = None,
                               round_num: int = 0) -> str:
    """Run the generator model — initial or revision."""
    is_revision = bool(previous_answer and flaws and round_num > 0)

    if is_revision:
        system_prompt = ic_phases.GENERATOR_REVISION_SYSTEM
        user_prompt = ic_phases.generator_revision_prompt(state, flaws, previous_answer, round_num)
    else:
        system_prompt = ic_phases.GENERATOR_INITIAL_SYSTEM
        user_prompt = ic_phases.generator_initial_prompt(state)

    services.log("IC", f"Generator {'revision' if is_revision else 'initial'}, round {round_num}", state)

    result = await services.call_llm(
        role="expert_1",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        state=state,
    )
    if result is None:
        raise RuntimeError("Generator LLM returned None")
    raw, _ = result
    try:
        data = extract_json(raw)
        return data.get("revised_answer", data.get("answer", ""))
    except Exception as exc:
        services.log("IC_ERROR", f"Generator JSON parse failed: {exc}", state)
        return previous_answer or "Error: could not parse generator output"


@dataclass(frozen=True)
class _JevScores:
    score: CriticDimensionScore
    model: str
    cost_usd: float | None
    latency_ms: int


def _accepts(score: CriticDimensionScore) -> bool:
    """The critic prompt's own ACCEPT rule: every dimension at ACCEPT_SCORE or above."""
    dims = (score.factuality, score.reasoning, score.completeness, score.helpfulness)
    return all(d >= ic_phases.ACCEPT_SCORE for d in dims)


async def _jev_scores(problem: str, answer: str, round_num: int) -> _JevScores | None:
    """Score *answer* on the critic's four dimensions with jev. Never raises.

    None -- the LLM critic decides -- when jev is off or has no port, when it
    fails or times out, or when problem + answer exceed JEV_MAX_STATE_CHARS.
    That last one skips rather than truncates: completeness judged on a
    cut-off answer is not a judgment of the answer.

    Jev is exempt from the presets' synthesis-bloc != scoring-bloc rule by the
    product owner's decision (2026-09-25). It is not a preset role, so the
    routing validator never sees it.
    """
    port = get_decision_port()
    if port is None or jev_mode() == "off":
        return None
    if len(problem) + len(answer) > JEV_MAX_STATE_CHARS:
        logger.info("jev_ic skipped round=%d: state over %d chars", round_num, JEV_MAX_STATE_CHARS)
        return None
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            port.decide({"problem": problem, "answer": answer}, ic_phases.JEV_CRITIC_QUESTIONS),
            timeout=JEV_CRITIC_TIMEOUT_SECONDS,
        )
        # Level position p (0..5, fractional between levels) stands for 2*p on 0-10.
        dims = {d: 2.0 * float(result.answers[d]["score"]) for d in ic_phases.JEV_CRITIC_QUESTIONS}
    except Exception as exc:
        logger.warning("jev_ic failed round=%d: %s: %s", round_num, type(exc).__name__, exc)
        return None
    return _JevScores(
        score=CriticDimensionScore(
            factuality=dims["factuality"],
            reasoning=dims["reasoning"],
            completeness=dims["completeness"],
            helpfulness=dims["clarity"],  # the same mapping _parse_critic_dimensions uses
        ),
        model=result.model,
        cost_usd=result.cost_usd,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def _log_jev_ic(
    state: PipelineState, round_num: int, mode: str, jev: _JevScores | None,
    llm: AdversarialRound | None,
) -> None:
    """One `jev_ic {...}` line per round jev was asked about. Never raises."""
    if jev is None:
        return
    try:
        def _dims(s: CriticDimensionScore | None) -> dict[str, float] | None:
            if s is None:
                return None
            return {"factuality": s.factuality, "reasoning": s.reasoning,
                    "completeness": s.completeness, "clarity": s.helpfulness}

        record = {
            "problem_sha": hashlib.sha256(state.problem.encode()).hexdigest()[:16],
            "round": round_num,
            "mode": mode,
            "source": "jev" if llm is None else "llm",
            "jev_scores": _dims(jev.score),
            "jev_accepts": _accepts(jev.score),
            "llm_verdict": llm.verdict if llm else None,
            "llm_scores": _dims(llm.critic_score) if llm else None,
            # Would jev's call have matched the LLM critic's? Only when both ran.
            "agree_accept": (_accepts(jev.score) == (llm.verdict == "ACCEPT")) if llm else None,
            "latency_ms": jev.latency_ms,
            "model": jev.model,
            "cost_usd": jev.cost_usd,
        }
        logger.info("jev_ic %s", json.dumps(record, sort_keys=True, default=str))
    except Exception as exc:
        logger.debug("jev_ic log failed: %s", exc)


async def run_critic_phase(state: PipelineState, services: WorkflowServices,
                            answer: str, round_num: int) -> AdversarialRound:
    """Evaluate the current answer.

    JEV_MODE=active: jev scores the four dimensions first. If every one clears
    ACCEPT_SCORE, the round is ACCEPT and the LLM critic does not run -- the
    loop ends, as it would on an LLM ACCEPT. Otherwise the LLM critic runs as
    before: a REVISE round needs its flaws, which the generator's revision and
    the stalemate check read, and jev writes no text.
    JEV_MODE=shadow: both run concurrently; the LLM's round is used, both logged.
    JEV_MODE=off (or no port): the LLM critic only.
    """
    mode = jev_mode()
    if mode == "shadow":
        jev, llm_round = await asyncio.gather(
            _jev_scores(state.problem, answer, round_num),
            _llm_critic_round(state, services, answer, round_num),
        )
        _log_jev_ic(state, round_num, mode, jev, llm_round)
        return llm_round

    jev = await _jev_scores(state.problem, answer, round_num) if mode == "active" else None
    if jev is not None and _accepts(jev.score):
        services.log("IC", f"Critic (jev) accepts round {round_num}", state)
        _log_jev_ic(state, round_num, mode, jev, None)
        return AdversarialRound(
            round_number=round_num,
            answer=answer,
            critic_model=jev.model,
            critic_score=jev.score,
            verdict="ACCEPT",
        )
    llm_round = await _llm_critic_round(state, services, answer, round_num)
    _log_jev_ic(state, round_num, mode, jev, llm_round)
    return llm_round


async def _llm_critic_round(state: PipelineState, services: WorkflowServices,
                            answer: str, round_num: int) -> AdversarialRound:
    """The LLM critic: scores, flaws and a verdict."""
    services.log("IC", f"Critic evaluating round {round_num}", state)

    result = await services.call_llm(
        role="expert_2",
        system_prompt=ic_phases.CRITIC_SYSTEM,
        user_prompt=ic_phases.critic_evaluation_prompt(state, answer, round_num),
        state=state,
    )
    if result is None:
        raise RuntimeError("Critic LLM returned None")
    raw, _ = result
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("IC_ERROR", f"Critic JSON parse failed: {exc}", state)
        # Return a default round with REVISE verdict to force another attempt
        return AdversarialRound(
            round_number=round_num,
            answer=answer,
            critic_score=CriticDimensionScore(factuality=5.0, reasoning=5.0, completeness=5.0, helpfulness=5.0),
            flaws_identified=[{"flaw": "Critic produced malformed JSON", "severity": "MEDIUM"}],
            verdict="REVISE",
        )

    scores = data.get("scores", {})
    return AdversarialRound(
        round_number=round_num,
        answer=answer,
        critic_score=_parse_critic_dimensions(scores),
        flaws_identified=data.get("flaws_identified", []),
        verdict=data.get("verdict", "REVISE"),
    )


async def run_synthesis_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Produce final synthesis from the complete debate trail."""
    services.log("IC", "Synthesizing debate trail", state)

    result = await services.call_llm(
        role="synthesis",
        system_prompt=ic_phases.SYNTHESIS_SYSTEM,
        user_prompt=ic_phases.synthesis_prompt(state),
        state=state,
    )
    if result is None:
        raise RuntimeError("Synthesis LLM returned None")
    raw, _ = result
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("IC_ERROR", f"Synthesis JSON parse failed: {exc}", state)
        if state.final_solution is None:
            from reasoner.domain.core_types import FinalSolution
            state.final_solution = FinalSolution(
                core_solution="", critical_insights=[], action_blueprint=[],
                open_questions=[], claim_labels=[], meta_audit=None,
            )
        state.final_solution.core_solution = "Synthesis parsing failed"
        return

    if state.final_solution is None:
        from reasoner.domain.core_types import FinalSolution
        state.final_solution = FinalSolution(
            core_solution="",
            critical_insights=[],
            action_blueprint=[],
            open_questions=[],
            claim_labels=[],
            meta_audit=None,
        )
    state.final_solution.core_solution = data.get("core_solution", "")

