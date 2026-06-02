from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

SOCRATIC_QUESTION_SYSTEM = "You are an analytical assistant. Ask probing questions to expose contradictions. Do not answer. Output ONLY valid JSON."

def socratic_question_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nGenerate 3-4 questions to challenge its assumptions.\n\nOutput JSON: {{"questions": [{{"id": "Q1", "text": "...", "target_assumption": "..."}}]}}'

SOCRATIC_ANSWER_SYSTEM = "You are an analytical assistant. Answer honestly and identify where your logic breaks. Output ONLY valid JSON."

def socratic_answer_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nSocratic Questions:\n{json.dumps(state.socratic_state["questions"], indent=2)}\n\nAttempt to answer, noting any contradictions (\'aporia\').\n\nOutput JSON: {{"answers": [{{"question_id": "Q1", "answer": "...", "contradiction_found": "..."}}]}}'
