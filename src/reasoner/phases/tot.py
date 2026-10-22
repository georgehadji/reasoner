from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)

TOT_DECOMPOSE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                        "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                        "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_decompose_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nDecompose the problem into a sequence of logical decision points.\n\nOutput JSON: {{"decision_points": [{{"id": "dp1", "description": "..."}}]}}'

TOT_GENERATE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                       "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                       "Any output that is not a strictly valid JSON object is a fatal error.")

def _tot_context(state: PipelineState) -> str:
    """The problem and the path chosen so far.

    The later ToT prompts carried neither, so each step reasoned about a
    decision point in a vacuum (docs/plans/audit-remediation-2-2026-10-20.md
    FLOW-6). The path is model-written, so it is wrapped (CLAUDE.md §5).
    """
    path = state.tot_state.get("current_path", [])
    path_block = (
        _wrap_external_content(json.dumps(path, ensure_ascii=False)) if path else "(none yet)"
    )
    return f'Problem: {_wrap_user_input(state.problem)}\n\nPath so far: {path_block}'


def tot_generate_prompt(state: PipelineState, current_dp: dict) -> str:
    decision_point = _wrap_external_content(json.dumps(current_dp, ensure_ascii=False))
    return f'{get_language_instruction(state)}\n\n{_tot_context(state)}\n\nDecision Point: {decision_point}\n\nGenerate candidate actions.\n\nOutput JSON: {{"candidates": ["action1", "action2"]}}'

TOT_EVALUATE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                       "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                       "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_evaluate_prompt(state: PipelineState, candidates: list[str]) -> str:
    wrapped = _wrap_external_content(json.dumps(candidates, ensure_ascii=False))
    return f'{get_language_instruction(state)}\n\n{_tot_context(state)}\n\nCandidates: {wrapped}\n\nEvaluate and score candidates (0.0-10.0).\n\nOutput JSON: {{"evaluations": [{{"candidate": "...", "score": 9.5, "verdict": "proceed"}}], "best_candidate": "..."}}'

TOT_BACKTRACK_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                        "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                        "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_backtrack_prompt(state: PipelineState) -> str:
    evaluations = _wrap_external_content(
        json.dumps(state.tot_state.get("evaluations", []), ensure_ascii=False)
    )
    return f'{get_language_instruction(state)}\n\n{_tot_context(state)}\n\nEvaluations: {evaluations}\n\nFinalize path based on evaluations.\n\nOutput JSON: {{"decision": "terminate|continue", "final_path": ["action1", "action2"], "confidence": 0.95}}'
