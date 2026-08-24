"""Shared Verbalized Sampling (VS) logic and prompts."""

from __future__ import annotations

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

# ─────────────────────────────────────────────────────────────────────────────
# Shared System Prompts
# ─────────────────────────────────────────────────────────────────────────────

VS_GENERATION_SYSTEM = (
    "You are a creative generator trained to explore unconventional solution spaces. "
    "Your goal is to produce a DIVERSE set of {task_name} — not the most obvious ones. "
    "Assign each {item_name} an approximate sampling probability: how likely a typical LLM "
    "would produce this exact output in a single shot. "
    "High probability = something any model would say; low probability = rare, creative, tail output. "
    "Deliberately include tail outputs (probability < {threshold}). "
    "Output ONLY valid JSON."
)

# ─────────────────────────────────────────────────────────────────────────────
# Shared Prompt Builders
# ─────────────────────────────────────────────────────────────────────────────

def build_vs_generation_prompt(
    state: PipelineState,
    task_name: str,
    item_name: str,
    round_num: int,
    k: int,
    threshold: float,
    n_tail: int,
    previous_outputs: list[dict],
    json_example: str,
    use_cot: bool = False,
) -> str:
    """Build a generic VS generation prompt."""
    lang = get_language_instruction(state)

    prev_section = ""
    if previous_outputs:
        titles = "\n".join(
            f"- {i.get('title', '?')}" if isinstance(i, dict) else f"- {i}"
            for i in previous_outputs
        )
        prev_section = (
            f"\n\nPreviously generated {item_name} (do NOT repeat; generate genuinely new ones):\n{titles}"
        )

    cot_prefix = (
        "Think step by step about the problem space, unusual angles, "
        "cross-domain analogies, and non-obvious constraints before generating.\n\n"
        if use_cot
        else ""
    )

    return (
        f"{lang}\n\n{cot_prefix}"
        f"Problem: {_wrap_user_input(state.problem)}"
        f"{prev_section}\n\n"
        f"Generate exactly {k} {item_name} for Round {round_num}. "
        f"Include at least {n_tail} items with probability below {threshold}.\n\n"
        f"Return JSON: {json_example}"
    )
