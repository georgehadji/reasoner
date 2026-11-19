"""Self-Refine -- one model drafts, scores its own answer, and revises until it scores 9/10.

Pattern: the same model drafts an answer, then evaluates it against a strict
rubric and returns a 0-10 score with concrete flaws. Below SR_TARGET_SCORE it
revises against its own flaws and is scored again. The loop ends at the target,
at the round limit, on a plateau, or when the time budget runs out.

The score is the model's self-assessment, not an independent measurement. Models
rate their own work high, so the evaluator is told to find flaws before it
scores, and the flow caps a score that sits next to a listed serious flaw.
Synthesis is told the score is self-reported.
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

GENERATOR_SYSTEM = (
    "You are an expert analytical assistant. Be thorough and precise, state what you do "
    "not know, and never invent facts or figures. Output ONLY valid JSON."
)

EVALUATOR_SYSTEM = (
    "You are a strict, sceptical evaluator of an answer. List the concrete flaws first "
    "(factual errors, logical gaps, missing cases, unsupported claims, ambiguity), then "
    "give an overall score from 0 to 10. 9 means a careful expert would change nothing "
    "material; 7 means sound with real gaps; 5 means significant problems. Do not "
    "inflate: a score of 9 or more with a serious flaw in your own list is inconsistent. "
    "Output ONLY valid JSON."
)

REVISION_SYSTEM = (
    "You are revising your own previous answer against the flaws found in it. Fix every "
    "flaw that is real; where a flaw is wrong, keep the original and say why. Produce a "
    "complete answer, not a patch. Output ONLY valid JSON."
)

SYNTHESIS_SYSTEM = (
    _UNIVERSAL_SYNTHESIS_SYSTEM
    + "\n\nSELF-REFINE SYNTHESIS: your input is a single model's answer, refined over "
    "rounds against its own scoring. The scores are SELF-REPORTED by the model that wrote "
    "the answer; they are evidence of effort, not verification, and no claim becomes "
    "VERIFIED because the model rated its answer highly. A flaw still listed in the last "
    "round belongs in open_questions or lowers the label of the claim it affects.\n\n"
    "core_solution IS the answer to the problem: the best answer's substance, corrected "
    "for its remaining flaws. Doubts go in open_questions and claim_labels alongside the "
    "answer, never in place of it."
)


def generator_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Decomposition:\n{_wrap_external_content(json.dumps(state.decomposition, indent=2))}\n\n'
        f'Produce a complete, well-reasoned answer.\n\n'
        f'Output JSON: {{"answer": "<complete answer>"}}'
    )


def evaluator_prompt(state: PipelineState, answer: str, round_num: int, target: float) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'ANSWER (round {round_num}):\n{_wrap_external_content(answer)}\n\n'
        f'Evaluate this answer. First list 1-5 concrete flaws, each with a severity and a '
        f'fix. Then score it 0-10 (the bar to stop is {target:g}).\n\n'
        f'Output JSON: {{"flaws": [{{"flaw": "...", "severity": "HIGH|MED|LOW", '
        f'"fix": "..."}}], "score": 0-10, "rationale": "..."}}'
    )


def revision_prompt(state: PipelineState, answer: str, flaws: list[dict], score: float) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'YOUR PREVIOUS ANSWER (self-scored {score:g}/10):\n{_wrap_external_content(answer)}\n\n'
        f'FLAWS YOU FOUND IN IT:\n{_wrap_external_content(json.dumps(flaws, indent=2))}\n\n'
        f'Write the complete revised answer.\n\n'
        f'Output JSON: {{"revised_answer": "<complete answer>"}}'
    )


def synthesis_prompt(state: PipelineState, sr: dict, best_answer: str) -> str:
    trail = [
        {"round": r["round"], "self_score": r.get("score"), "flaws": (r.get("flaws") or [])[:3]}
        for r in sr.get("rounds", [])
    ]
    reached = sr.get("target_reached", False)
    note = "" if reached else (
        f'The model never reached its own target (stop reason: {sr.get("stop_reason") or "none"}). '
        f'Do not present the answer as settled; carry the flaws of the best round into '
        f'open_questions.\n\n'
    )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Self-scoring trail ({len(trail)} rounds, target reached: {reached}):\n'
        f'{_wrap_external_content(json.dumps(trail, indent=2))}\n\n'
        f'Best answer (self-scored {sr.get("best_score")}/10):\n'
        f'{_wrap_external_content(best_answer)}\n\n'
        f'{note}'
        f'Produce the final synthesis.\n\n'
        f'{SYNTHESIS_OUTPUT_FORMAT}'
    )
