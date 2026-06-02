from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

DEBATE_OPENING_SYSTEM = "You are an expert debater. Your objective is to present a compelling, evidence-based opening argument for your assigned stance. Focus on making strong claims, supported by logic and any provided context. Do NOT describe the debate process or your role; execute your role as a debater. Output ONLY valid JSON."

def debate_opening_prompt(state: PipelineState, side: str, stance: str) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nYou are Side {side}. Your assigned stance is: {stance}.\nPresent your opening statement defending this specific stance.\n\nOutput JSON: {{"side": "{side}", "stance": "{stance}", "content": "<your statement>", "key_claims": ["<claim 1>"]}}'

DEBATE_REBUTTAL_SYSTEM = "You are an expert debater. Your objective is to rigorously attack your opponent's opening statement, exposing its weaknesses, logical fallacies, or lack of evidence. Simultaneously, you must defend your own key claims from potential attacks. CRITICAL RULE: Do NOT be neutral or conciliatory. Your tone must be adversarial. Do NOT describe the debate process or your role; execute your role as a debater. Output ONLY valid JSON."

def debate_rebuttal_prompt(state: PipelineState, side: str, opponent_statement: str) -> str:
    return f'{get_language_instruction(state)}\n\nYour opponent\'s statement:\n{opponent_statement}\n\nYou are Side {side}. Present your rebuttal.\n\nOutput JSON: {{"side": "{side}", "rebuttal_content": "<your rebuttal>", "target_flaws": ["<flaw 1>"]}}'

DEBATE_JUDGE_SYSTEM = "You are an analytical assistant. Evaluate the debate and render a verdict. Output ONLY valid JSON."

def debate_judge_prompt(state: PipelineState) -> str:
    return f'{get_language_instruction(state)}\n\nDebate Transcript:\n{json.dumps(state.debate_rounds, indent=2)}\n\nScore both sides and declare a winner.\n\nOutput JSON: {{"scores": ..., "verdict_rationale": "..."}}'

DEBATE_CROSS_SYSTEM = "You are an analytical assistant. Challenge specific claims with evidence. Be precise and direct. Output ONLY valid JSON."

def debate_cross_examine_prompt(state: PipelineState, side: str, opponent_claims: list) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'You are Side {side}. Your opponent made these claims:\n'
        f'{json.dumps(opponent_claims, indent=2)}\n\n'
        f'Challenge each claim with counter-evidence or logical contradiction.\n\n'
        f'Output JSON: {{"side": "{side}", "challenges": ['
        f'{{"claim": "<claim>", "challenge": "<counter-evidence>", "verdict": "REFUTED|WEAKENED|STANDS"}}]}}'
    )
