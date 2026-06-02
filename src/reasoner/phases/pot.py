from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.phases._shared import get_language_instruction, _wrap_user_input, _wrap_external_content

POT_GENERATE_SYSTEM = (
    "You are an expert programmer. Generate Python code to solve the given quantitative problem. "
    "The code should be self-contained, use only standard library, and include comments. "
    + JSON_ONLY_FOOTER
)

def pot_generate_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Write Python code to solve this problem computationally. '
        f'The code must be self-contained, use only Python standard library, '
        f'and handle edge cases. Include print statements for the final result. '
        f'Also provide a brief explanation of the approach.\n\n'
        f'Output JSON: {{"code": "<python code as string>", '
        f'"explanation": "<approach explanation>", '
        f'"expected_output_type": "<number|list|dict|boolean>"}}'
    )

POT_EXECUTE_SYSTEM = (
    "You are a code execution engine. Simulate or describe the execution of the given Python code. "
    "If actual execution is unavailable, trace through the code logically and produce the output. "
    + JSON_ONLY_FOOTER
)

def pot_execute_prompt(state: PipelineState) -> str:
    code = state.pot_state.get("code", "")
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Execute the following Python code and return the exact output. '
        f'If the code has errors, return the error message. '
        f'Trace through the execution step by step if needed.\n\n'
        f'Code:\n```python\n{code}\n```\n\n'
        f'Output JSON: {{"output": "<execution output>", '
        f'"success": true, '
        f'"error": "<error message if any>", '
        f'"intermediate_steps": ["<step result>"]}}'
    )

POT_INTERPRET_SYSTEM = (
    "You are an analytical interpreter. Given code execution results, explain what they mean "
    "in the context of the original problem. " + JSON_ONLY_FOOTER
)

def pot_interpret_prompt(state: PipelineState) -> str:
    code = state.pot_state.get("code", "")
    output = state.pot_state.get("execution_output", "")
    error = state.pot_state.get("execution_error", "")
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Generated Code:\n```python\n{code}\n```\n\n'
        f'Execution Output:\n{_wrap_external_content(output)}\n\n'
        f'Error (if any): {_wrap_external_content(error)}\n\n'
        f'Interpret the execution results in the context of the original problem. '
        f'Explain what the output means, whether it fully answers the problem, '
        f'and what limitations or caveats exist.\n\n'
        f'Output JSON: {{"interpretation": "<explanation>", '
        f'"answer": "<final answer to the problem>", '
        f'"caveats": ["<caveat>"], '
        f'"confidence": 0.9}}'
    )
