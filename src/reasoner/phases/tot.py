from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

TOT_DECOMPOSE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                        "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                        "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_decompose_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nDecompose the problem into a sequence of logical decision points.\n\nOutput JSON: {{"decision_points": [{{"id": "dp1", "description": "..."}}]}}'

TOT_GENERATE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                       "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                       "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_generate_prompt(state: PipelineState, current_dp: dict) -> str:
    return f'{get_language_instruction(state)}\n\nDecision Point: {json.dumps(current_dp)}\n\nGenerate candidate actions.\n\nOutput JSON: {{"candidates": ["action1", "action2"]}}'

TOT_EVALUATE_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                       "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                       "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_evaluate_prompt(state: PipelineState, candidates: list[str]) -> str:
    return f'{get_language_instruction(state)}\n\nCandidates: {json.dumps(candidates)}\n\nEvaluate and score candidates (0.0-10.0).\n\nOutput JSON: {{"evaluations": [{{"candidate": "...", "score": 9.5, "verdict": "proceed"}}], "best_candidate": "..."}}'

TOT_BACKTRACK_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                        "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                        "Any output that is not a strictly valid JSON object is a fatal error.")

def tot_backtrack_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nFinalize path based on evaluations.\n\nOutput JSON: {{"decision": "terminate|continue", "final_path": ["action1", "action2"], "confidence": 0.95}}'
