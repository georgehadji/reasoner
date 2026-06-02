"""Iterative Critique (LLM Debate) — Phase Logic & Convergence Detection.

Author: DeepSeek TUI — June 2026

Iterative Critique phase logic — adversarial back-and-forth with convergence detection.

Pattern: generator produces answer → critic finds flaws → generator revises → loop until convergence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import CriticDimensionScore
from reasoner.application.flows.base import WorkflowServices
from reasoner.parsing import extract_json
import reasoner.phases.iterative_critique as ic_phases

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


def _parse_critic_dimensions(scores: dict) -> CriticDimensionScore:
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


async def run_critic_phase(state: PipelineState, services: WorkflowServices,
                            answer: str, round_num: int) -> AdversarialRound:
    """Run the critic model — evaluate the current answer."""
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

