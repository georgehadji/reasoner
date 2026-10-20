"""Iterative Critique (LLM Debate) — Adversarial Refinement Through Runtime Harness Adaptation.

Pattern: Two models from different AI labs debate until convergence.
Generator (Model A) produces answers. Critic (Model B) identifies flaws.
Generator revises addressing each flaw. Loop continues until the critic
accepts, scores plateau, or max rounds exhaust.

Design Philosophy: "Adapt the interface, not the model." Rather than
training a specialized debate model, this runtime harness wraps existing
LLMs with prompt orchestration, convergence detection, and cross-lab
diversity to produce adversarial refinement behavior.

Author: DeepSeek TUI — June 2026
"""
from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)
from reasoner.phases._universal import SYNTHESIS_OUTPUT_FORMAT
from reasoner.phases._universal import SYNTHESIS_SYSTEM as _UNIVERSAL_SYNTHESIS_SYSTEM

GENERATOR_INITIAL_SYSTEM = (
    "You are an expert analytical assistant engaged in an iterative refinement process. "
    "Be thorough, precise, and cite evidence where possible. Output ONLY valid JSON."
)

GENERATOR_REVISION_SYSTEM = (
    "You are revising a previous answer based on specific criticism. "
    "For each flaw, you MUST: 1. Acknowledge it explicitly, 2. State AGREE or DISAGREE, "
    "3. If agreeing: explain how you fixed it, 4. If disagreeing: provide counter-argument. "
    "Do NOT simply rephrase. Output ONLY valid JSON."
)

CRITIC_SYSTEM = (
    "You are an expert analytical critic. Rigorously evaluate an answer for: "
    "factual errors, logical fallacies, missing edge cases, ambiguity, hidden assumptions. "
    "Score 0-10. Always find at least one improvement. Output ONLY valid JSON."
)

SYNTHESIS_SYSTEM = (
    _UNIVERSAL_SYNTHESIS_SYSTEM
    + "\n\nDEBATE SYNTHESIS: your input is the trail of an adversarial debate between a "
    "generator and a critic from different labs. Treat the critic's flaws as claims to "
    "weigh, not as settled facts, and give the generator's pushback its due. A flaw that "
    "was raised and never shown to be fixed belongs in open_questions or lowers the label "
    "of the claim it affects. A debate that stopped without the critic's acceptance has "
    "not settled the question; say so plainly."
)

# The critic's ACCEPT rule. Rendered into critic_evaluation_prompt below, and
# applied in code to jev's scores (application/flows/iterative_critique_phases)
# -- one rule, whichever model scored the round.
ACCEPT_SCORE = 8

# JEV_MODE=active/shadow: the four dimensions the LLM critic scores, restated as
# typed questions for a System One model. Six anchored levels stand for 0, 2,
# 4, 6, 8 and 10; the caller maps level position p to 2*p. Level 4 -- "only
# small, non-substantive improvements remain" -- is what ACCEPT_SCORE means.
_JEV_LEVELS = [
    "0 unacceptable: fundamentally wrong, or does not address it at all",
    "2 poor: major problems that change the conclusion",
    "4 weak: several significant problems",
    "6 adequate: moderate problems a careful reviewer would still send back",
    "8 strong: only small, non-substantive improvements remain",
    "10 excellent: nothing a careful expert would insist on changing",
]
_JEV_DIMENSIONS = {
    "factuality": "are its factual claims correct, with no fabricated facts or figures?",
    "reasoning": "is the logic sound -- no fallacies, unsupported leaps or hidden assumptions?",
    "completeness": "does it cover everything the problem asks, including important edge cases?",
    "clarity": "is it unambiguous and easy to act on?",
}
JEV_CRITIC_QUESTIONS: dict[str, dict] = {
    dim: {
        "type": "score",
        "instructions": (
            f"Judge the `answer` as a response to the `problem`. {dim.capitalize()}: {question}"
        ),
        "criteria": _JEV_LEVELS,
    }
    for dim, question in _JEV_DIMENSIONS.items()
}


def generator_initial_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Decomposition:\n{_wrap_external_content(json.dumps(state.decomposition, indent=2))}\n\n'
        f'Produce a complete, well-reasoned solution.\n\n'
        f'Output JSON: {{"answer": "<solution>", "key_claims": [...], '
        f'"confidence": 0.0-1.0, "approach_summary": "<method>"}}'
    )


def generator_regenerate_prompt(
    state: PipelineState, rejected_answer: str, flaws
) -> str:
    """A fresh attempt after the critic REJECTed the approach.

    Same task as the initial prompt, plus the rejected approach and the critic's
    flaws framed as pitfalls: without them a fresh run tends to reproduce the
    answer that was just rejected.
    """
    pitfalls = json.dumps(
        {"rejected_approach": (rejected_answer or "")[:600], "flaws": flaws}, indent=2
    )
    return (
        f'{generator_initial_prompt(state)}\n\n'
        f'A previous attempt was REJECTED as fundamentally wrong. Take a different '
        f'approach and avoid these pitfalls; do not reuse the rejected approach:\n'
        f'{_wrap_external_content(pitfalls)}'
    )


def critic_evaluation_prompt(state: PipelineState, answer: str, round_num: int) -> str:
    previous_flaws = ""
    if round_num > 1 and state.adversarial_rounds:
        prev = state.adversarial_rounds[-1]
        previous_flaws = (
            f"\nPrevious flaws (check if addressed):\n"
            f"{_wrap_external_content(json.dumps(prev.flaws_identified, indent=2))}"
        )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'ANSWER (Round {round_num}):\n{_wrap_external_content(answer)}\n\n'
        f'{previous_flaws}\n\n'
        f'Score dimensions: factuality, reasoning, completeness, clarity (0-10 each). '
        f'Identify 1-3 specific flaws. '
        f'If all scores >= {ACCEPT_SCORE}: verdict=ACCEPT. '
        f'If improvable: REVISE. If wrong: REJECT.\n\n'
        f'Output JSON: {{"critic_model": "<name>", '
        f'"scores": {{"factuality": N, "reasoning": N, "completeness": N, "clarity": N}}, '
        f'"flaws_identified": [{{"flaw": "...", "severity": "HIGH|MED|LOW", "evidence": "..."}}], '
        f'"verdict": "ACCEPT|REVISE|REJECT", "rationale": "..."}}'
    )


def generator_revision_prompt(state: PipelineState, flaws, previous_answer: str, round_num: int) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'YOUR PREVIOUS ANSWER:\n{_wrap_external_content(previous_answer)}\n\n'
        f'CRITIC FLAWS (Round {round_num}):\n'
        f'{_wrap_external_content(json.dumps(flaws, indent=2))}\n\n'
        f'For each flaw: state AGREE/DISAGREE, if AGREE explain fix, if DISAGREE provide evidence. '
        f'Then produce COMPLETE revised answer.\n\n'
        f'Output JSON: {{"flaw_responses": [{{"flaw": "...", "stance": "AGREE|DISAGREE", '
        f'"response": "..."}}], "revised_answer": "<complete solution>", '
        f'"changes_summary": "<what changed>", "confidence": 0.0-1.0}}'
    )


def synthesis_prompt(state: PipelineState) -> str:
    rounds_summary = []
    for r in state.adversarial_rounds:
        rounds_summary.append({
            "round": r.round_number,
            "verdict": r.verdict,
            "score_total": r.critic_score.total if r.critic_score else 0.0,
            "answer_snippet": r.answer[:300] if r.answer else "",
            "flaws": r.flaws_identified[:3],
            "changes": r.changes_summary or "",
            # Flaws the generator pushed back on: synthesis should weigh them
            # rather than treat every critic flaw as upheld.
            "rejected_flaws": [
                fr for fr in (r.flaw_responses or [])
                if str(fr.get("stance", "")).upper() == "DISAGREE"
            ],
        })

    convergence_reason = getattr(state, "adversarial_convergence_reason", "")
    convergence_round = getattr(state, "adversarial_convergence_round", 0)

    unresolved = unresolved_flaws(state)
    unresolved_block = ""
    if unresolved or convergence_reason != "critic_accepted":
        unresolved_block = (
            f'The critic did NOT accept the final answer (reason: {convergence_reason or "none"}). '
            f'Flaws it still lists, none shown to be resolved:\n'
            f'{_wrap_external_content(json.dumps(unresolved, indent=2))}\n'
            f'Carry each into open_questions, or label the claim it affects HYPOTHESIS or '
            f'UNKNOWN. Do not present the answer as settled.\n\n'
        )

    msg = (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Debate Trail ({len(state.adversarial_rounds)} rounds, '
        f'converged: {getattr(state, "adversarial_converged", False)}, '
        f'reason: {convergence_reason}):\n'
        f'{_wrap_external_content(json.dumps(rounds_summary, indent=2))}\n\n'
        f'Best Answer:\n{_wrap_external_content(_get_best_answer(state))}\n\n'
        f'{unresolved_block}'
        f'Produce the final synthesis incorporating all improvements '
        f'(debate converged at round {convergence_round}).\n\n'
        f'{SYNTHESIS_OUTPUT_FORMAT}'
    )
    return msg


def unresolved_flaws(state: PipelineState) -> list[str]:
    """Flaws the last real critic round raised, unless the debate ended in ACCEPT.

    Degraded rounds carry a placeholder flaw, not a critic judgement, so the
    last non-degraded round is the one that counts.
    """
    if getattr(state, "adversarial_convergence_reason", "") == "critic_accepted":
        return []
    for r in reversed(state.adversarial_rounds):
        if getattr(r, "degraded", False):
            continue
        flaws = (str(f.get("flaw", "")).strip() for f in r.flaws_identified if isinstance(f, dict))
        return [f for f in flaws if f]
    return []


def _get_best_answer(state: PipelineState) -> str:
    if not state.adversarial_rounds:
        return ""
    best = max(state.adversarial_rounds,
               key=lambda r: r.critic_score.total if r.critic_score else 0.0)
    return best.answer or best.revised_answer
