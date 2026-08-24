from __future__ import annotations

import json

from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

SD_SELECT_SYSTEM = (
    "You are a meta-reasoning architect. Given a problem, select the reasoning modules "
    "that are most appropriate from the available inventory. " + JSON_ONLY_FOOTER
)

def sd_select_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Available reasoning modules:\n'
        f'- decomposition: break problem into sub-problems\n'
        f'- verification: fact-check claims\n'
        f'- analogy: find cross-domain parallels\n'
        f'- causal_analysis: identify cause-effect chains\n'
        f'- counterfactual: explore what-if scenarios\n'
        f'- abstraction: extract deep structure\n'
        f'- constraint_satisfaction: respect hard limits\n'
        f'- optimization: find best allocation\n\n'
        f'Select 3-5 modules that are MOST relevant to this problem. '
        f'Explain why each is needed and in what order they should be applied.\n\n'
        f'Output JSON: {{"selected_modules": [{{'
        f'"module": "<module_name>", '
        f'"rationale": "<why needed>", '
        f'"order": 1'
        f'}}], '
        f'"composition_strategy": "<how modules interact>"}}'
    )

SD_ADAPT_SYSTEM = (
    "You are a prompt engineer. Adapt the selected reasoning modules into concrete prompts "
    "and instructions for the current problem. " + JSON_ONLY_FOOTER
)

def sd_adapt_prompt(state: PipelineState) -> str:
    modules = state.self_discover_state.get("selected_modules", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Selected Modules: {json.dumps(modules, indent=2)}\n\n'
        f'Adapt each selected module into a concrete instruction or prompt '
        f'specific to this problem. The adapted instructions should be actionable '
        f'and clearly define inputs/outputs for each module.\n\n'
        f'Output JSON: {{"adapted_modules": [{{'
        f'"module": "<module_name>", '
        f'"instruction": "<concrete instruction>", '
        f'"input": "<what this module receives>", '
        f'"output": "<what this module produces>"'
        f'}}]}}'
    )

SD_IMPLEMENT_SYSTEM = (
    "You are an execution engine. Execute the adapted reasoning modules in sequence "
    "and synthesize their outputs into a final answer. " + JSON_ONLY_FOOTER
)

def sd_implement_prompt(state: PipelineState) -> str:
    adapted = state.self_discover_state.get("adapted_modules", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Adapted Module Instructions: {json.dumps(adapted, indent=2)}\n\n'
        f'Execute each module in sequence, passing outputs from one to the next. '
        f'After all modules complete, synthesize their collective output into a '
        f'coherent final answer. Document the contribution of each module.\n\n'
        f'Output JSON: {{"module_outputs": [{{'
        f'"module": "<name>", '
        f'"output": "<result>"'
        f'}}], '
        f'"final_answer": "<synthesized answer>", '
        f'"module_attribution": {{"<module>": "<contribution summary>"}}, '
        f'"confidence": 0.85}}'
    )
