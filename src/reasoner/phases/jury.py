from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

JURY_GENERATOR_SYSTEM = ("You are an analytical assistant. You MUST produce a valid JSON object ONLY. "
                           "Do not include any introductory text, concluding remarks, or conversational markdown (e.g., ```json). "
                           "Any output that is not a strictly valid JSON object is a fatal error.")

def jury_generator_prompt(state: PipelineState, generator_id: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n'
        f'Decomposition:\n{json.dumps(state.decomposition, indent=2)}\n\n'
        f'You are {generator_id}. Generate a complete, well-reasoned solution.\n\n'
        f'Output JSON: {{"generator_id": "{generator_id}", '
        f'"solution": "<full solution text>", '
        f'"approach_summary": "<1-2 sentence summary of your approach>", '
        f'"confidence": <0.0-1.0 self-assessed confidence>, '
        f'"key_claims": ["<verifiable claim 1>", "<verifiable claim 2>"]}}'
    )

JURY_CRITIC_SYSTEM = "You are an analytical assistant. Score each candidate against the provided guidelines. Output ONLY valid JSON."

def jury_critic_prompt(state: PipelineState) -> str:
    candidates_summary = [{"generator_id": c.generator_id, "approach": c.approach_summary} for c in state.generation_candidates]
    gen_ids = [c.generator_id for c in state.generation_candidates]
    ranking_example = json.dumps(gen_ids)
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Jury Guidelines:\n{json.dumps(state.jury_guidelines)}\n\n'
        f'Candidates:\n{json.dumps(candidates_summary, indent=2)}\n\n'
        f'Score each candidate on factuality, reasoning, completeness, helpfulness (0-10 each).\n\n'
        f'CONFIDENCE vs ACCURACY: Reward honest uncertainty. If a candidate states confident claims '
        f'that are factually wrong or unsubstantiated, apply a confidence_vs_accuracy_penalty (0.0-10.0) '
        f'inside that candidate\'s score entry.\n\n'
        f'Output JSON:\n'
        f'{{"critic_id": "<critic_id>", '
        f'"critic_model": "<model name>", '
        f'"candidate_scores": {{'
        f'"<generator_id>": {{'
        f'"factuality": <0-10>, '
        f'"reasoning": <0-10>, '
        f'"completeness": <0-10>, '
        f'"helpfulness": <0-10>, '
        f'"confidence_vs_accuracy_penalty": <0.0-10.0>, '
        f'"bias_flags": [], '
        f'"steel_man": "<strongest charitable interpretation of this candidate — best case FOR it>"'
        f'}}}}, '
        f'"ranking": {ranking_example}, '
        f'"dissenting_note": "<any notable disagreement or caveat>"}}'
    )

JURY_VERIFIER_SYSTEM = "You are an analytical assistant. Verify these claims. Output ONLY valid JSON."

def jury_verifier_prompt(state: PipelineState) -> str:
    all_claims = [{"claim": claim, "source": gc.generator_id} for gc in state.generation_candidates for claim in gc.key_claims]
    return f'{get_language_instruction(state)}\n\nVerify these claims:\n{json.dumps(all_claims, indent=2)}\n\nOutput JSON: {{"verifications": [{{"claim": "...", "verdict": "VERIFIED|...", "evidence": "..."}}]}}'

JURY_META_EVAL_SYSTEM = "You are an analytical assistant. Assess reliability and bias. Output ONLY valid JSON."

def jury_meta_eval_prompt(state: PipelineState) -> str:
    from dataclasses import asdict
    return f'{get_language_instruction(state)}\n\nEvaluate the critics based on their scores:\n{json.dumps([asdict(cs) for cs in state.critic_scores], indent=2)}\n\nAssess critic reliability, bias, and agreement rate.\n\nOutput JSON: {{"critic_reliability": {{...}}, "meta_insight": "..."}}'
