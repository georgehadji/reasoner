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
    # OpenAI — GPT
    "gpt-5": "openai", "gpt-5.5": "openai", "gpt-5.5-pro": "openai",
    "gpt-5-mini": "openai", "gpt-5.4-mini": "openai", "gpt-5.4-nano": "openai",
    "gpt-latest": "openai", "gpt-mini-latest": "openai",
    "gpt-4o-mini": "openai", "o3": "openai", "o3-mini": "openai",
    "gpt-oss-120b": "openai", "gpt-oss-20b": "openai",
    # Google — Gemini
    "gemini-flash": "google", "gemini-pro-real": "google",
    "gemini-flash-lite-real": "google", "gemini-2.5-flash-lite": "google",
    "gemini-pro-latest": "google", "gemini-flash-latest": "google",
    "gemini-flash-image": "google", "gemini-pro-image": "google",
    "gemini-3.1-flash-image-preview": "google", "gemini-3.1-flash-lite-image": "google",
    # Note: gemini-pro → Anthropic (claude-sonnet), gemini-flash-lite → Qwen (qwen3.5-flash)
    # Meta
    "llama-3.3-70b": "meta",
    # Mistral
    "mistral-large-3": "mistral", "mistral-small": "mistral",
    "ministral-8b": "mistral", "codestral-2508": "mistral",
    # DeepSeek
    "deepseek-v4-pro": "deepseek", "deepseek-v4-flash": "deepseek",
    # Qwen (Alibaba)
    "qwen3-max": "qwen", "qwen3.7-max": "qwen", "qwen3.7-plus": "qwen", "qwen3.5-flash": "qwen",
    "qwen3-max-thinking": "qwen", "qwen3.6-flash": "qwen", "qwen3.6-plus-real": "qwen",
    "qwen3-coder-flash": "qwen", "qwen3-coder-30b-a3b": "qwen",
    # GLM (Zhipu)
    "glm-5.2": "zhipu",
    # MiniMax
    "minimax-m3": "minimax", "minimax-m2.7": "minimax", "minimax-m2.5": "minimax",
    "minimax-m2.1": "minimax", "minimax-m2": "minimax", "minimax-m1": "minimax",
    # Moonshot (Kimi)
    "kimi-k2-6": "moonshot",
    # StepFun
    "stepfun-3.7-flash": "stepfun",
    # OpenAI — Codex
    "gpt-5.1-codex-mini": "openai",
    # Google — misc
    "google/gemma-2-9b-it": "google", "gemini-flash-lite": "qwen",
    "gemini-pro": "anthropic", "gemini-pro-image": "google",
    # NVIDIA
    "nvidia-nemotron-super": "nvidia",
    # Sourceful
    "riverflow-v2-fast-preview": "sourceful",
    # InclusionAI (Ant Group)
    "ring-2.6-1t": "inclusionai", "ling-2.6-flash-free": "inclusionai",
    # Xiaomi — MiMo
    "mimo-v2.5-pro": "xiaomi", "mimo-v2.5": "xiaomi",
    "mimo-v2-pro": "xiaomi", "mimo-v2-flash": "xiaomi",
    # xAI — Grok
    "grok-4.20": "xai", "grok-4.20-multi-agent": "xai", "grok-4.3": "xai",
    "grok-build-0.1": "xai",
    # Perplexity
    "sonar-pro": "perplexity", "sonar-pro-search": "perplexity",
    "sonar": "perplexity", "sonar-reasoning-pro": "perplexity", "sonar-deep-research": "perplexity",
    # NVIDIA
    "nemotron-3-ultra-free": "nvidia", "nemotron-3-super-free": "nvidia",
    "nemotron-nano-omni-free": "nvidia", "nemotron-nano-30b-free": "nvidia",
    "llama-nemotron-super-49b": "nvidia",
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
