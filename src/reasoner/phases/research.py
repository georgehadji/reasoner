from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

DEEP_RESEARCH_SYSTEM = (
    "You are an analytical research assistant. Your goal is to gather high-quality, "
    "verifiable external sources to answer the user's problem. You MUST NOT rely on "
    "your internal training knowledge — always verify claims with external sources. "
    "Output ONLY valid JSON."
)

def deep_research_prompt(state: PipelineState, current_knowledge: list[dict], iteration: int, max_iterations: int) -> str:
    knowledge_str = json.dumps(current_knowledge, indent=2) if current_knowledge else "No information gathered yet."
    source_count = len(current_knowledge)
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Iteration: {iteration} of {max_iterations}\n'
        f'Sources gathered so far: {source_count}\n\n'
        f'Current Knowledge Gathered:\n{knowledge_str}\n\n'
        f'RULES:\n'
        f'1. You MUST continue searching until you have gathered at least 5 relevant, '
        f'high-quality external sources, OR until you reach the maximum iterations.\n'
        f'2. Do NOT declare "done" just because you have internal knowledge on the topic.\n'
        f'3. Generate up to 3 highly specific, targeted search queries that will find '
        f'authoritative sources (academic papers, reputable news, expert blogs).\n'
        f'4. Avoid generic queries like "AI" or "technology". Be specific to the problem.\n\n'
        f'Output JSON: {{"action": "search|done", "queries": ["<query1>", "<query2>"], "reasoning": "<why you chose this action>"}}'
    )
