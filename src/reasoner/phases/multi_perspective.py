from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.constants import TRUNCATION
from reasoner.phases._shared import get_language_instruction, _followup_context, _wrap_user_input

PERSPECTIVE_SYSTEMS = {
    "constructive": "Respond in the same language as the user's problem. Build the strongest, most comprehensive solution. Analyze from first principles, cite historical precedents where relevant, and address 2nd-order consequences. Minimum 4 paragraphs. JSON only.",
    "destructive": "Respond in the same language as the user's problem. Find every flaw in the proposed approach or subject matter. Focus exclusively on substantive weaknesses, risks, and incorrect assumptions. Do NOT criticize the prompt's language, grammar, formatting, or mixed languages. JSON only.",
    "systemic": "Respond in the same language as the user's problem. Find 2nd/3rd-order effects. JSON only.",
    "minimalist": "Respond in the same language as the user's problem. Apply Occam's Razor. Simplest 80% solution. JSON only.",
}

def perspective_prompt(state: PipelineState, perspective: str) -> str:
    context = {"problem": _wrap_user_input(state.problem[:TRUNCATION.PROMPT])}
    if state.decomposition:
        context["chain"] = len(state.decomposition.get("causal_chain", []))
    if state.reflexion_memory:
        context["memory"] = state.reflexion_memory[:TRUNCATION.MEMORY]
    followup = _followup_context(state)
    
    return f'{get_language_instruction(state)}\n\nContext: {json.dumps(context)}{followup}\n\nAnalyze from {perspective} perspective.\n\nYou MUST return EXACTLY this JSON structure with no additional keys. Put all analysis inside "core_analysis" as a single string (3-6 paragraphs). Label factual claims inline with [VERIFIED], [HYPOTHESIS], or [UNKNOWN].\n\nJSON: {{"perspective": "{perspective}", "core_analysis": "<your detailed analysis with inline epistemic labels>", "key_insights": ["<insight 1>", "<insight 2>", "<insight 3>"]}}'

CRITIQUE_SYSTEM = "You are an analytical assistant. Score solutions honestly. Output ONLY valid JSON."

def critique_prompt(state: PipelineState) -> str:
    candidates_summary = [
        {"perspective": c.perspective.value, "one_liner": c.content[:TRUNCATION.API_STORAGE], "key_insights": c.key_insights[:TRUNCATION.MEMORY]}
        for c in state.candidates
    ]
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Evaluate these candidates:\n{json.dumps(candidates_summary, indent=2)}\n\n'
        f'Score each candidate on ALL four dimensions (0-10 each). '
        f'Provide a "steel_man" (strongest charitable interpretation — best case FOR each candidate) for each.\n\n'
        f'CRITICAL SCORING: If a candidate states confident claims that are factually wrong or unsubstantiated, '
        f'apply a confidence_vs_accuracy_penalty (0.0-10.0). Reward honest uncertainty over false confidence.\n\n'
        f'Output JSON (ALL fields required for EVERY score entry):\n'
        f'{{"scores": [{{'
        f'"perspective": "<p_val>", '
        f'"logical_consistency": <0-10>, '
        f'"evidence_support": <0-10>, '
        f'"failure_resilience": <0-10>, '
        f'"feasibility": <0-10>, '
        f'"confidence_vs_accuracy_penalty": <0.0-10.0>, '
        f'"steel_man": "<strongest charitable interpretation of this candidate — best case FOR it>", '
        f'"bias_flags": ["<bias if any>"]'
        f'}}]}}'
    )

STRESS_SYSTEM = "You are an analytical assistant. Simulate adversarial conditions. Be specific about real-world failure mechanics. Output ONLY valid JSON."

def stress_test_prompt(state: PipelineState) -> str:
    top_candidates_summary = [
        {"perspective": c.perspective.value, "one_liner": c.content[:TRUNCATION.ASSUMPTION]}
        for c in state.top_candidates
    ]
    task_type_str = state.task_type.value if hasattr(state.task_type, 'value') else str(state.task_type)
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem Domain: {_wrap_user_input(state.problem[:TRUNCATION.API_STORAGE])}\n'
        f'Task Type: {task_type_str}\n\n'
        f'Test these solutions under optimal, constraint_violation, and adversarial scenarios:\n'
        f'{json.dumps(top_candidates_summary, indent=2)}\n\n'
        f'CRITICAL INSTRUCTION: Scenarios MUST be highly specific to the Problem Domain and Task Type. Do NOT generate generic business risks (like supply-chain collapse) unless they directly apply to the specific problem. Describe concrete failure mechanics relevant to the domain.\n'
        f'Do NOT describe LLM processing errors like truncation, formatting issues, length limits, or off-topic responses. '
        f'Output JSON: {{"stress_tests": [{{"scenario": "<name>", "survival_rate": <0.0-1.0>, "failure_mode": "<desc>"}}]}}'
    )
