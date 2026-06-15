"""HarnessGuard — invariant validation for governed harness mutations (#4).

Paper grounding: §3.5.3 — hard invariant guard: a mutation may not reduce
Phase-2 cross-lab diversity below preset minima or remove a fallback chain's
cross-lab terminal.
"""

from __future__ import annotations

from reasoner.domain.harness_metrics import HarnessMutation
from reasoner.core.evolution_constants import (
    EVOLUTION_MIN_CROSS_LAB_DIVERSITY,
    EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL,
)

# Mapping of model aliases → training ecosystem (lab).
# Used by the invariant guard to verify cross-lab diversity is preserved.
_MODEL_LABS: dict[str, str] = {
    # Anthropic
    "claude-sonnet": "anthropic", "claude-haiku": "anthropic",
    # OpenAI
    "gpt-5": "openai", "gpt-5-mini": "openai", "o3": "openai",
    # Google
    "gemini-flash": "google", "gemini-pro": "google",
    # Meta
    "llama-3.3-70b": "meta",
    # Mistral
    "mistral-large-3": "mistral", "mistral-small": "mistral",
    # DeepSeek
    "deepseek-v3": "deepseek", "deepseek-r1": "deepseek",
    # Qwen (Alibaba)
    "qwen3.7-max": "qwen", "qwen3.7-plus": "qwen", "qwen3.5-flash": "qwen",
    # GLM (Zhipu)
    "glm-5.1": "zhipu", "glm-4-air": "zhipu",
    # MiniMax
    "minimax-m3": "minimax", "minimax-m2.5": "minimax",
    # Moonshot (Kimi)
    "kimi-k2-6": "moonshot",
    # StepFun
    "stepfun-3.7-flash": "stepfun",
    # InclusionAI (Ant Group)
    "ring-2.6-1t": "inclusionai", "ling-2.6-flash-free": "inclusionai",
    # Xiaomi
    "mimo-v2-flash": "xiaomi", "mimo-v2-pro": "xiaomi",
    # NVIDIA
    "nemotron-3-ultra-free": "nvidia",
}


def get_model_lab(model_alias: str) -> str:
    """Return the training ecosystem for a model alias.

    Unknown models default to "unknown" so they don't crash the guard
    but also don't count toward diversity.
    """
    return _MODEL_LABS.get(model_alias, "unknown")


def check_mutation_invariants(
    mutation: HarnessMutation,
    current_models: list[str],
    proposed_models: list[str],
) -> tuple[bool, str]:
    """Check that a proposed mutation preserves hard invariants.

    Args:
        mutation: The proposed harness mutation.
        current_models: Model aliases currently in use for this routing role.
        proposed_models: Model aliases after the mutation would be applied.

    Returns:
        (accepted: bool, reason: str) — False + reason if an invariant would
        be violated.
    """
    # Invariant 1: cross-lab diversity must not fall below minimum
    current_labs = {get_model_lab(m) for m in current_models}
    proposed_labs = {get_model_lab(m) for m in proposed_models}
    current_diversity = len(current_labs)
    proposed_diversity = len(proposed_labs)

    if proposed_diversity < EVOLUTION_MIN_CROSS_LAB_DIVERSITY:
        return False, (
            f"Mutation would reduce cross-lab diversity from {current_diversity} "
            f"to {proposed_diversity} (min {EVOLUTION_MIN_CROSS_LAB_DIVERSITY} required). "
            f"Labs: {proposed_labs}"
        )

    # Invariant 2: fallback chain terminal must be cross-lab (if required)
    if EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL and len(proposed_models) >= 2:
        primary_lab = get_model_lab(proposed_models[0])
        fallback_labs = {get_model_lab(m) for m in proposed_models[1:]}
        if primary_lab in fallback_labs:
            return False, (
                f"Fallback terminal {proposed_models[-1]} is same lab ({primary_lab}) "
                f"as primary {proposed_models[0]}. Cross-lab fallback required."
            )

    # Invariant 3: cost-tier mutations require risk_tier="cost" or "safety"
    if "cost" in mutation.target.lower() or "spend" in mutation.target.lower():
        if mutation.risk_tier == "safe":
            return False, (
                f"Cost-affecting mutation targeting '{mutation.target}' must be "
                f"risk_tier='cost' or 'safety', not '{mutation.risk_tier}'."
            )

    return True, ""
