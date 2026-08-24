from __future__ import annotations

import json

from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)

SOT_SKELETON_SYSTEM = (
    "You are an expert problem decomposer. Generate a skeleton outline of sub-problems "
    "that collectively solve the main problem. Each sub-problem should be independent "
    "and solvable in parallel. " + JSON_ONLY_FOOTER
)

def sot_skeleton_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Decompose this problem into 3-5 sub-problems that can be solved independently '
        f'and in parallel. Each sub-problem should have a clear scope, inputs, and expected output. '
        f'The sub-problems should collectively cover all aspects of the main problem.\n\n'
        f'Output JSON: {{"sub_problems": [{{'
        f'"id": "1", '
        f'"description": "<sub-problem>", '
        f'"inputs": ["<input>"], '
        f'"expected_output": "<output description>", '
        f'"rationale": "<why this decomposition>"'
        f'}}]}}'
    )

SOT_SOLVE_SYSTEM = (
    "You are a specialist solver. Solve the assigned sub-problem thoroughly and concisely. "
    + JSON_ONLY_FOOTER
)

def sot_solve_prompt(state: PipelineState, sub_problem: dict) -> str:
    skeleton = state.sot_state.get("sub_problems", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Full Skeleton: {json.dumps(skeleton, indent=2)}\n\n'
        f'YOUR ASSIGNED SUB-PROBLEM:\n'
        f'ID: {sub_problem.get("id", "?")}\n'
        f'Description: {sub_problem.get("description", "")}\n'
        f'Inputs: {json.dumps(sub_problem.get("inputs", []))}\n'
        f'Expected Output: {sub_problem.get("expected_output", "")}\n\n'
        f'Solve this sub-problem thoroughly. Your solution will be combined with others '
        f'to form the complete answer.\n\n'
        f'Output JSON: {{"sub_problem_id": "{sub_problem.get("id", "")}", '
        f'"solution": "<detailed solution>", '
        f'"key_insights": ["<insight>"], '
        f'"assumptions": ["<assumption>"]}}'
    )

SOT_ASSEMBLE_SYSTEM = (
    "You are a master synthesizer. Combine multiple sub-problem solutions into a coherent, "
    "unified answer. Ensure smooth transitions and resolve any contradictions. " + JSON_ONLY_FOOTER
)

def sot_assemble_prompt(state: PipelineState) -> str:
    solutions = state.sot_state.get("solutions", [])
    solutions_json = json.dumps(solutions, indent=2) if solutions else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Sub-problem Solutions:\n{_wrap_external_content(solutions_json)}\n\n'
        f'Assemble these sub-problem solutions into a single, coherent, comprehensive answer. '
        f'Ensure smooth transitions between sections, resolve any contradictions, '
        f'and maintain logical flow. The assembled answer should stand alone.\n\n'
        f'Output JSON: {{"assembled_answer": "<full unified answer>", '
        f'"transitions": ["<how sections connect>"], '
        f'"resolved_conflicts": ["<conflict and resolution>"], '
        f'"meta_observation": "<insight about the whole>"}}'
    )
