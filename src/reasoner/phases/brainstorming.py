"""Verbalized Sampling brainstorming phase prompts and prompt builders.

VS (Verbalized Sampling) asks an LLM to generate k ideas *with* their approximate
sampling probabilities.  Assigning probabilities forces the model to introspect its
own distribution and deliberately include tail ideas (low-probability = rare/creative)
that mode-collapsed aligned models would normally suppress.

Reference: "Verbalized Sampling: How to Mitigate Mode Collapse and Unlock LLM Diversity"
"""

from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

# ─────────────────────────────────────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────────────────────────────────────

VS_GENERATION_SYSTEM = (
    "You are a creative idea generator trained to explore unconventional solution spaces. "
    "Your goal is to produce a DIVERSE set of ideas — not the most obvious ones. "
    "Assign each idea an approximate sampling probability: how likely a typical LLM "
    "would produce this exact idea in a single shot. "
    "High probability = something any model would say; low probability = rare, creative, tail idea. "
    "Deliberately include tail ideas (probability < {threshold}). "
    "Output ONLY valid JSON."
)

VS_CLUSTER_SYSTEM = (
    "You are an idea analyst. Given a pool of brainstormed ideas, your job is to: "
    "(1) detect and merge near-duplicate ideas, "
    "(2) cluster the remaining ideas into 3-5 thematic groups, "
    "(3) score each unique idea on feasibility (0-10), novelty (0-10), and impact (0-10). "
    "Prefer ideas with high novelty — conventional ideas score lower regardless of feasibility. "
    "Output ONLY valid JSON."
)

VS_DEVELOP_SYSTEM = (
    "You are a strategic developer. For each selected idea, produce a complete development: "
    "use case narrative, implementation sketch (3-5 concrete steps), key risks, and success criteria. "
    "Be specific. Avoid generic advice. "
    "Output ONLY valid JSON."
)

VS_SYNTHESIS_SYSTEM = (
    "You are a synthesis strategist. Given a set of deeply developed brainstormed ideas, "
    "your job is to produce a final integrated synthesis: identify the single strongest direction "
    "or portfolio of complementary ideas, extract non-obvious cross-idea insights, and produce "
    "a concrete action blueprint. Be decisive — rank and recommend, do not list without judgment. "
    "CRITICAL RULE: Your final recommendation and all insights MUST be derived EXCLUSIVELY from the "
    "provided 'Developed ideas' context. Do NOT introduce external concepts or information. "
    "Ground your entire analysis in the provided text. "
    "Output ONLY valid JSON."
)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────────────────────────────────────

def vs_generation_prompt(
    state: PipelineState,
    round_num: int,
    k: int,
    threshold: float,
    n_tail: int,
    previous_ideas: list[dict],
    use_cot: bool = False,
) -> str:
    """Build the VS idea-generation prompt for one round."""
    lang = get_language_instruction(state)

    prev_section = ""
    if previous_ideas:
        titles = "\n".join(
            f"- {i.get('title', '?')}" if isinstance(i, dict) else f"- {i}"
            for i in previous_ideas
        )
        prev_section = (
            f"\n\nPreviously generated ideas (do NOT repeat; generate genuinely new ones):\n{titles}"
        )

    cot_prefix = (
        "Think step by step about the problem space, unusual angles, "
        "cross-domain analogies, and non-obvious constraints before generating ideas.\n\n"
        if use_cot
        else ""
    )

    json_example = (
        f'{{"ideas": [{{"id": "R{round_num}I1", "title": "...", '
        f'"description": "...", "probability": 0.08, '
        f'"creativity_tier": "conventional|lateral|disruptive", '
        f'"core_insight": "one-sentence novelty hook"}}]}}'
    )

    return (
        f"{lang}\n\n{cot_prefix}"
        f"Problem: {_wrap_user_input(state.problem)}"
        f"{prev_section}\n\n"
        f"Generate exactly {k} ideas for Round {round_num}. "
        f"Include at least {n_tail} ideas with probability below {threshold}.\n\n"
        f"Return JSON: {json_example}"
    )


def vs_cluster_prompt(state: PipelineState, all_ideas: list[dict]) -> str:
    """Build the clustering + scoring prompt from the raw idea pool."""
    lang = get_language_instruction(state)
    ideas_json = json.dumps(all_ideas, ensure_ascii=False, indent=2)
    n = len(all_ideas)

    json_schema = (
        f'{{"clusters": [{{"theme": "...", "ideas": ['
        f'{{"id": "...", "title": "...", "feasibility": 7, "novelty": 9, "impact": 8, "keep": true}}'
        f']}}], "deduplicated_count": {n}}}'
    )

    return (
        f"{lang}\n\n"
        f"Problem: {_wrap_user_input(state.problem)}\n\n"
        f"Raw idea pool ({n} ideas):\n{ideas_json}\n\n"
        f"Deduplicate, cluster into 3-5 themes, and score each idea. "
        f"Mark the best idea(s) per cluster with keep=true.\n\n"
        f"Return JSON: {json_schema}"
    )


def vs_synthesis_prompt(state: PipelineState, developments: list[dict], clusters: list[dict]) -> str:
    """Build the final synthesis prompt from developed ideas and cluster themes."""
    lang = get_language_instruction(state)
    devs_json = json.dumps(developments, ensure_ascii=False, indent=2)
    cluster_themes = [c.get("theme", "") for c in clusters if c.get("theme")]
    themes_str = (
        "Themes explored: " + ", ".join(cluster_themes) + "\n\n"
        if cluster_themes else ""
    )

    return (
        f"{lang}\n\n"
        f"Problem: {_wrap_user_input(state.problem)}\n\n"
        f"{themes_str}"
        f"Developed ideas ({len(developments)} total):\n{devs_json}\n\n"
        f"Synthesize these developments into a final integrated recommendation. "
        f"Identify the strongest idea(s), extract 3-5 non-obvious cross-idea insights, "
        f"and produce a concrete action blueprint (2-4 steps with time horizons).\n\n"
        f'Return JSON: {{'
        f'"core_solution": "integrated recommendation narrative (3-5 sentences)", '
        f'"critical_insights": ["insight 1", "insight 2"], '
        f'"action_blueprint": [{{"action": "...", "time_horizon": "...", "go_criteria": "...", "fallback": "..."}}], '
        f'"open_questions": ["question 1"], '
        f'"most_dangerous_assumption": "...", '
        f'"dominant_bias": "...", '
        f'"remaining_uncertainty": "..."'
        f"}}"
    )


def vs_develop_prompt(state: PipelineState, top_ideas: list[dict]) -> str:
    """Build the deep-development prompt for the selected top ideas."""
    lang = get_language_instruction(state)
    ideas_json = json.dumps(top_ideas, ensure_ascii=False, indent=2)
    return (
        f"{lang}\n\n"
        f"Problem: {_wrap_user_input(state.problem)}\n\n"
        f"Develop each of these {len(top_ideas)} selected ideas in detail:\n{ideas_json}\n\n"
        f'Return JSON: {{"developments": ['
        f'{{"id": "...", "title": "...", "use_case": "...", '
        f'"steps": ["Step 1: ...", "Step 2: ..."], '
        f'"risks": ["..."], "success_criteria": ["..."]}}'
        f"]}}"
    )
