from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

TOT_DECOMPOSE_SYSTEM = (
    "You are a strategic planner. Decompose the problem into sequential decision points. "
    + JSON_ONLY_FOOTER
)

def tot_decompose_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Identify the key sequential decision points in this problem. '
        f'Each decision point should have 2-3 possible candidate actions. '
        f'Limit to at most 3 decision points to control token cost.\n\n'
        f'Output JSON: {{"decision_points": [{{'
        f'"id": "dp1", '
        f'"description": "<what decision must be made>", '
        f'"candidates": [{{"action": "<action>", "rationale": "<why>"}}]'
        f'}}]}}'
    )

TOT_GENERATE_SYSTEM = (
    "You are a creative strategist. Generate diverse candidate next-steps for the given decision point. "
    + JSON_ONLY_FOOTER
)

def tot_generate_prompt(state: PipelineState, decision_point: dict) -> str:
    path_so_far = state.tot_state.get("current_path", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Decisions made so far: {json.dumps(path_so_far, indent=2)}\n\n'
        f'Current Decision Point: {decision_point.get("description", "")}\n\n'
        f'Generate 2-3 diverse, high-quality candidate actions for this decision point. '
        f'Each candidate should represent a genuinely different strategic direction.\n\n'
        f'Output JSON: {{"candidates": [{{'
        f'"candidate_id": "c1", '
        f'"action": "<action description>", '
        f'"expected_outcome": "<what happens>", '
        f'"risks": ["<risk>"], '
        f'"prerequisites": ["<prerequisite>"]'
        f'}}]}}'
    )

TOT_EVALUATE_SYSTEM = (
    "You are a critical evaluator. Score each candidate action on multiple dimensions. "
    + JSON_ONLY_FOOTER
)

def tot_evaluate_prompt(state: PipelineState, candidates: list) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Candidate Actions:\n{json.dumps(candidates, indent=2)}\n\n'
        f'Evaluate EACH candidate on a scale of 0-10 for: '
        f'feasibility, expected_value, risk_level (lower is better), and alignment_with_goal. '
        f'Recommend the best candidate and explain why.\n\n'
        f'Output JSON: {{"evaluations": [{{'
        f'"candidate_id": "c1", '
        f'"feasibility": 8, '
        f'"expected_value": 7, '
        f'"risk_level": 4, '
        f'"alignment_with_goal": 9, '
        f'"score": 7.5, '
        f'"verdict": "<proceed|reject|caution>"'
        f'}}], '
        f'"best_candidate": "<candidate_id>", '
        f'"recommendation": "<explanation>"}}'
    )

TOT_BACKTRACK_SYSTEM = (
    "You are a strategic analyst. Given evaluation results, decide whether to proceed, "
    "backtrack, or terminate. " + JSON_ONLY_FOOTER
)

def tot_backtrack_prompt(state: PipelineState) -> str:
    path = state.tot_state.get("current_path", [])
    evaluations = state.tot_state.get("evaluations", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Current path: {json.dumps(path, indent=2)}\n\n'
        f'Evaluations: {json.dumps(evaluations, indent=2)}\n\n'
        f'Based on the evaluations, decide: (1) CONTINUE with the best candidate, '
        f'(2) BACKTRACK to a previous decision point and try a different branch, or '
        f'(3) TERMINATE with the current path as the final solution. '
        f'Provide reasoning.\n\n'
        f'Output JSON: {{"decision": "<continue|backtrack|terminate>", '
        f'"target_decision_point": "<if backtracking, which dp>", '
        f'"reasoning": "<why>", '
        f'"final_path": ["<action>"], '
        f'"confidence": 0.8}}'
    )
