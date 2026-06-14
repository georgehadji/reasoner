from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

DEBATE_OPENING_SYSTEM = ("You are an expert debater. You MUST produce a valid JSON object ONLY. "
                           "Do not include any introductory text, concluding remarks, or conversational markdown. "
                           "Any output that is not a strictly valid JSON object is a fatal error.")

def debate_opening_prompt(state: PipelineState, side: str, stance: str) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nYou are Side {side}. Your assigned stance is: {stance}.\nPresent your opening statement defending this specific stance.\n\nOutput JSON: {{"side": "{side}", "stance": "{stance}", "content": "<your statement>", "key_claims": ["<claim 1>"]}}'

DEBATE_REBUTTAL_SYSTEM = ("You are an expert debater. You MUST produce a valid JSON object ONLY. "
                          "Do not include any introductory text, concluding remarks, or conversational markdown. "
                          "Any output that is not a strictly valid JSON object is a fatal error.")

def debate_rebuttal_prompt(state: PipelineState, side: str, opponent_statement: str) -> str:
    return f'{get_language_instruction(state)}\n\nYour opponent\'s statement:\n{opponent_statement}\n\nYou are Side {side}. Present your rebuttal.\n\nOutput JSON: {{"side": "{side}", "rebuttal_content": "<your rebuttal>", "target_flaws": ["<flaw 1>"]}}'

DEBATE_JUDGE_SYSTEM = (
    "You are a neutral debate judge. You MUST produce a valid JSON object ONLY. "
    "Do not include any introductory text, concluding remarks, or conversational markdown. "
    "Any output that is not a strictly valid JSON object is a fatal error.\n\n"
    "SCORING RUBRIC (each dimension 0-10):\n"
    "- logical_consistency: Soundness and internal coherence of the argument.\n"
    "- evidence_support: Quality and strength of supporting evidence.\n"
    "- failure_resilience: Ability to withstand counterarguments.\n"
    "- feasibility: Practical applicability of the proposed solution.\n\n"
    "SIDE MAPPING:\n"
    '- Side A (proposition) → perspective: "constructive"\n'
    '- Side B (opposition) → perspective: "destructive"'
)

def debate_judge_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Debate Transcript:\n{json.dumps(state.debate_rounds, indent=2)}\n\n'
        f'Score both sides and declare a winner.\n\n'
        f'IMPORTANT: Use exactly "constructive" for Side A (proposition) '
        f'and "destructive" for Side B (opposition) as the perspective field.\n\n'
        f'Output JSON:\n'
        f'{{\n'
        f'  "scores": [\n'
        f'    {{\n'
        f'      "perspective": "constructive",\n'
        f'      "logical_consistency": <float 0-10>,\n'
        f'      "evidence_support": <float 0-10>,\n'
        f'      "failure_resilience": <float 0-10>,\n'
        f'      "feasibility": <float 0-10>,\n'
        f'      "bias_flags": ["<flag if any>"],\n'
        f'      "steel_man": "<strongest point in favour of this side>"\n'
        f'    }},\n'
        f'    {{\n'
        f'      "perspective": "destructive",\n'
        f'      "logical_consistency": <float 0-10>,\n'
        f'      "evidence_support": <float 0-10>,\n'
        f'      "failure_resilience": <float 0-10>,\n'
        f'      "feasibility": <float 0-10>,\n'
        f'      "bias_flags": ["<flag if any>"],\n'
        f'      "steel_man": "<strongest point in favour of this side>"\n'
        f'    }}\n'
        f'  ],\n'
        f'  "winner": "A" | "B" | "DRAW",\n'
        f'  "verdict_rationale": "<concise reasoning>"\n'
        f'}}'
    )

DEBATE_CROSS_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                       "Do not include any introductory text, concluding remarks, or conversational markdown. "
                       "Any output that is not a strictly valid JSON object is a fatal error.")

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
