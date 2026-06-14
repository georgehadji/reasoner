from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

SCIENTIFIC_HYPOTHESIS_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                                "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                                "Any output that is not a strictly valid JSON object is a fatal error.")

def scientific_hypothesis_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nObservations: {_wrap_user_input(state.problem)}\n\nGenerate 3 competing hypotheses.\n\nOutput JSON: {{"hypotheses": [{{"id": "H1", "statement": "...", "falsifiability": "..."}}]}}'

SCIENTIFIC_TEST_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                          "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                          "Any output that is not a strictly valid JSON object is a fatal error. "
                          "CRITICAL RULE: Do NOT automatically assume all hypotheses are falsified. You MUST evaluate them logically against common knowledge and any provided context. A hypothesis can be SUPPORTED, WEAKENED, or FALSIFIED.")

def scientific_test_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nHypotheses:\n{json.dumps(state.scientific_state["hypotheses"], indent=2)}\n\nFor each, describe a test and predict the result (SUPPORTED, WEAKENED, FALSIFIED).\n\nOutput JSON: {{"test_results": [{{"hypothesis_id": "H1", "experiment": "...", "result": "..."}}]}}'
