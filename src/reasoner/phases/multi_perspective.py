from __future__ import annotations

import json

from reasoner.core.constants import TRUNCATION
from reasoner.core.vs_constants import (
    VS_CRITIQUE_STRESS_SEED_TOP_N,
    VS_K_CRITIQUE_HYPOTHESES,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    _followup_context,
    _wrap_external_content,
    _wrap_user_input,
    build_memory_context,
    build_web_sources_block,
    get_language_instruction,
)

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
    # Web sources and recalled memory are web- or model-authored text, so they are
    # rendered through the shared delimited builders instead of being interpolated
    # raw into the JSON context blob. Both return "" when empty.
    web_block = build_web_sources_block(state)
    memory_block = build_memory_context(state)

    # W2 premise audit (docs/plans/sycophancy-mitigation.md §2c): only the
    # destructive perspective sees the user-origin premises, and only to attack
    # the framing — the other three perspectives stay blind to this, preserving
    # the Phase-2 independence invariant (docs/MIND_VIRUS_MITIGATION.md).
    premises_block = ""
    if perspective == "destructive" and state.decomposition:
        raw_assumptions = (
            state.decomposition.get("assumptions", [])
            if isinstance(state.decomposition, dict)
            else getattr(state.decomposition, "assumptions", None) or []
        )
        if raw_assumptions:
            from reasoner.core.parsing import _parse_premises
            user_premises = [
                p for p in _parse_premises(raw_assumptions)
                if p.origin in ("user_stated", "user_implied")
            ]
            if user_premises:
                claims = "\n".join(f'- {p.text} (label: {p.label.value})' for p in user_premises)
                premises_block = _wrap_external_content(
                    "\n[USER PREMISES]\n"
                    "These are claims the user supplied, not established facts. Attack the "
                    "framing: which of these, if false, changes the answer, and what is the "
                    "strongest reason to doubt each one? Do not attack the user.\n"
                    f"{claims}\n"
                )

    return f'{get_language_instruction(state)}\n{followup}{memory_block}\nContext: {json.dumps(context)}{web_block}{premises_block}\n\nAnalyze from {perspective} perspective.\n\nYou MUST return EXACTLY this JSON structure with no additional keys. Put all analysis inside "core_analysis" as a single string (3-6 paragraphs). Label factual claims inline with [VERIFIED], [HYPOTHESIS], or [UNKNOWN].\n\nJSON: {{"perspective": "{perspective}", "core_analysis": "<your detailed analysis with inline epistemic labels>", "key_insights": ["<insight 1>", "<insight 2>", "<insight 3>"]}}'

CRITIQUE_SYSTEM = "You are an analytical assistant. Score solutions honestly. Output ONLY valid JSON."

def _vs_hypotheses_instruction() -> str:
    """Verbalized-Sampling block appended to the critique prompt (premium tier).

    Asks the critic to verbalize a probability-ranked distribution of distinct
    failure hypotheses spanning the whole candidate set, each with falsifying
    evidence and a concrete check. This is orthogonal to per-candidate scoring
    and exists to counter "looks good overall" review mode collapse.
    """
    return (
        f'\n\nADDITIONALLY, perform a Verbalized-Sampling failure audit across ALL '
        f'candidates combined. Generate up to {VS_K_CRITIQUE_HYPOTHESES} INDEPENDENT, '
        f'NON-OVERLAPPING failure hypotheses — distinct suspected flaws, risks, or '
        f'wrong assumptions in the proposed solutions. Rank them by probability '
        f'(descending). For each hypothesis assign a probability (0.0-1.0) that it '
        f'is a real problem, and provide both supporting AND contradicting evidence '
        f'plus a concrete test that would falsify it. Make the hypotheses '
        f'substantially different from each other — do not restate one flaw in '
        f'multiple forms.\n\n'
        f'Add this top-level key to your JSON output:\n'
        f'"review_hypotheses": [{{'
        f'"claim": "<the suspected flaw or risk>", '
        f'"probability": <0.0-1.0>, '
        f'"severity": "HIGH|MED|LOW", '
        f'"evidence_for": "<what supports it>", '
        f'"evidence_against": "<what argues against it>", '
        f'"verification": "<concrete test/check to confirm or falsify it>", '
        f'"cost_if_wrong": "<impact if shipped uncaught>"'
        f'}}]'
    )


def critique_prompt(state: PipelineState, with_hypotheses: bool = False) -> str:
    candidates_summary = [
        {"perspective": c.perspective.value, "one_liner": c.content[:TRUNCATION.API_STORAGE], "key_insights": c.key_insights[:TRUNCATION.MEMORY]}
        for c in state.candidates
    ]
    base = (
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
    if with_hypotheses:
        base += _vs_hypotheses_instruction()
    return base

STRESS_SYSTEM = "You are an analytical assistant. Simulate adversarial conditions. Be specific about real-world failure mechanics. Output ONLY valid JSON."

def stress_test_prompt(state: PipelineState) -> str:
    top_candidates_summary = [
        {"perspective": c.perspective.value, "one_liner": c.content[:TRUNCATION.ASSUMPTION]}
        for c in state.top_candidates
    ]
    task_type_str = state.task_type.value if hasattr(state.task_type, 'value') else str(state.task_type)

    # VS handoff: seed stress scenarios from the highest-probability critique
    # hypotheses so Phase-4 verifies the flaws the critic already flagged rather
    # than rediscovering generic risks. No-op when review_hypotheses is empty.
    seed_block = ""
    hypotheses = getattr(state, "review_hypotheses", []) or []
    if hypotheses:
        seeds = [
            {
                "claim": h.claim,
                "severity": h.severity,
                "verification": h.verification,
            }
            for h in hypotheses[:VS_CRITIQUE_STRESS_SEED_TOP_N]
        ]
        seed_block = (
            f'\n\nPRIORITY FAILURE HYPOTHESES (from critique — design at least one '
            f'scenario that exercises each):\n{json.dumps(seeds, indent=2)}\n'
        )

    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem Domain: {_wrap_user_input(state.problem[:TRUNCATION.API_STORAGE])}\n'
        f'Task Type: {task_type_str}\n\n'
        f'Test these solutions under optimal, constraint_violation, and adversarial scenarios:\n'
        f'{json.dumps(top_candidates_summary, indent=2)}\n'
        f'{seed_block}\n'
        f'CRITICAL INSTRUCTION: Scenarios MUST be highly specific to the Problem Domain and Task Type. Do NOT generate generic business risks (like supply-chain collapse) unless they directly apply to the specific problem. Describe concrete failure mechanics relevant to the domain.\n'
        f'Do NOT describe LLM processing errors like truncation, formatting issues, length limits, or off-topic responses. '
        f'Output JSON: {{"stress_tests": [{{"scenario": "<name>", "survival_rate": <0.0-1.0>, "failure_mode": "<desc>"}}]}}'
    )
