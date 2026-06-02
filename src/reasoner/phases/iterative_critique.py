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
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

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
    "You are an analytical assistant. Review the debate trail and produce the final answer. "
    "Output ONLY valid JSON."
)


def generator_initial_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Decomposition:\n{json.dumps(state.decomposition, indent=2)}\n\n'
        f'Produce a complete, well-reasoned solution.\n\n'
        f'Output JSON: {{"answer": "<solution>", "key_claims": [...], '
        f'"confidence": 0.0-1.0, "approach_summary": "<method>"}}'
    )


def critic_evaluation_prompt(state: PipelineState, answer: str, round_num: int) -> str:
    previous_flaws = ""
    if round_num > 1 and state.adversarial_rounds:
        prev = state.adversarial_rounds[-1]
        previous_flaws = (
            f"\nPrevious flaws (check if addressed):\n"
            f"{json.dumps(prev.flaws_identified, indent=2)}"
        )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'ANSWER (Round {round_num}):\n{answer}\n\n'
        f'{previous_flaws}\n\n'
        f'Score dimensions: factuality, reasoning, completeness, clarity (0-10 each). '
        f'Identify 1-3 specific flaws. '
        f'If all scores >= 8: verdict=ACCEPT. If improvable: REVISE. If wrong: REJECT.\n\n'
        f'Output JSON: {{"critic_model": "<name>", '
        f'"scores": {{"factuality": N, "reasoning": N, "completeness": N, "clarity": N}}, '
        f'"flaws_identified": [{{"flaw": "...", "severity": "HIGH|MED|LOW", "evidence": "..."}}], '
        f'"verdict": "ACCEPT|REVISE|REJECT", "rationale": "..."}}'
    )


def generator_revision_prompt(state: PipelineState, flaws, previous_answer: str, round_num: int) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'YOUR PREVIOUS ANSWER:\n{previous_answer}\n\n'
        f'CRITIC FLAWS (Round {round_num}):\n{json.dumps(flaws, indent=2)}\n\n'
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
        })

    convergence_reason = getattr(state, "adversarial_convergence_reason", "")
    convergence_round = getattr(state, "adversarial_convergence_round", 0)
    
    msg = (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Debate Trail ({len(state.adversarial_rounds)} rounds, '
        f'converged: {getattr(state, "adversarial_converged", False)}, '
        f'reason: {convergence_reason}):\n'
        f'{json.dumps(rounds_summary, indent=2)}\n\n'
        f'Best Answer:\n{_get_best_answer(state)}\n\n'
        f'Produce final synthesis incorporating all improvements.\n\n'
        f'Output JSON: {{"core_solution": "<final answer>", '
        f'"convergence_round": {convergence_round}, '
        f'"convergence_reason": "{convergence_reason}", '
        f'"total_rounds": {len(state.adversarial_rounds)}, '
        f'"improvement_trajectory": "<how answer evolved>"}}'
    )
    return msg


def _get_best_answer(state: PipelineState) -> str:
    if not state.adversarial_rounds:
        return ""
    best = max(state.adversarial_rounds,
               key=lambda r: r.critic_score.total if r.critic_score else 0.0)
    return best.revised_answer or best.answer
