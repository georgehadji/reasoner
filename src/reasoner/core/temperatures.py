"""Single source of truth for LLM temperature + reasoning-effort per phase.

Two orthogonal knobs control reasoning quality vs. cost per phase:

1. ``temperature`` — sampling randomness. Applies to *non-reasoning* models and
   to hybrid models in their non-thinking mode. Reasoning-only models (OpenAI
   gpt-5.x / o-series, claude-opus-4.8, claude-fable-5) ignore or reject it.

2. ``reasoning.effort`` — how many thinking tokens the model spends before
   answering. This is the correct knob for reasoning models, normalized by
   OpenRouter across providers (OpenAI effort levels, Anthropic max_tokens,
   Gemini thinking levels). Values: max | xhigh | high | medium | low |
   minimal | none.

Reasoning-model temperature note:
   For models that DO accept temperature but run an internal chain-of-thought
   (DeepSeek R1/V3.2, Qwen-thinking, Grok-4.x, GLM-5.x, Kimi-thinking), very low
   temperatures degrade reasoning. DeepSeek explicitly recommends ~0.6 for R1.
   We therefore floor the effective temperature for reasoning models at
   ``REASONING_TEMPERATURE_FLOOR`` so structured phases (critic=0.1, verifier=0.2)
   don't starve a reasoning model's exploration.
"""

from __future__ import annotations

# ── Optimal temperatures per reasoning phase ────────────────────────────────
# Low  (0.1-0.4) : consistency / structured output (classification, scoring)
# Mid  (0.5)     : systematic rigor with minor variability (stress, synthesis)
# High (0.7-1.0) : creative exploration (perspectives, generators)
PHASE_TEMPERATURES: dict[str, float] = {
    "classification":   0.3,
    "decomposition":    0.4,
    "fusion":           0.2,

    "perspective":      1.0,
    "scoring":          0.3,
    "stress_testing":   0.5,
    "synthesis":        0.5,
    "generator":        0.7,
    "critic":           0.1,
    "verifier":         0.2,
    "meta_evaluator":   0.3,
    "context_vetting":  0.3,
    "recovery_path":    0.2,
    "primary":          0.7,   # fallback for generic primary calls
    "research":         0.3,
    "deep_read":        0.2,
}

# Non-phase contexts (search query generation, neuro memory ops, etc.)
NON_PHASE_TEMPERATURES: dict[str, float] = {
    "search_query_generation": 0.3,
    "neuro_memory":            0.3,
}

# ── Reasoning effort per phase ──────────────────────────────────────────────
# Only applied to reasoning-capable models (OpenRouter ignores it otherwise).
# Cheap structured phases use minimal/low effort to avoid burning thinking
# tokens; judgment- and integration-heavy phases use high effort.
PHASE_REASONING_EFFORT: dict[str, str] = {
    "classification":   "minimal",   # fast routing, no deep thought needed
    "decomposition":    "low",       # structure extraction
    "fusion":           "minimal",   # mechanical merge
    "context_vetting":  "low",

    "perspective":      "medium",    # some reasoning aids cross-lab diversity
    "generator":        "medium",
    "scoring":          "high",      # careful independent judgment
    "critic":           "high",
    "verifier":         "high",
    "meta_evaluator":   "high",
    "stress_testing":   "high",      # adversarial depth
    "synthesis":        "high",      # evidence integration + epistemic labeling
    "research":         "medium",
    "deep_read":        "medium",
    "recovery_path":    "low",
}

# Reasoning models perform poorly at very low temperature. When a reasoning
# model is routed to a low-temp structured phase, raise its effective
# temperature to at least this floor (DeepSeek R1 guidance ≈ 0.6).
REASONING_TEMPERATURE_FLOOR: float = 0.6


def temperature_for(phase: str, *, is_reasoning_model: bool = False) -> float:
    """Resolve the effective temperature for a phase.

    Applies REASONING_TEMPERATURE_FLOOR when the routed model runs an internal
    chain-of-thought, so low structured-phase temps don't starve it.
    """
    base = PHASE_TEMPERATURES.get(phase, PHASE_TEMPERATURES["primary"])
    if is_reasoning_model and base < REASONING_TEMPERATURE_FLOOR:
        return REASONING_TEMPERATURE_FLOOR
    return base


def reasoning_extra_body(phase: str) -> dict[str, dict[str, str]] | None:
    """Return an OpenRouter ``extra_body`` reasoning override for a phase.

    Returns ``{"reasoning": {"effort": <level>}}`` or None when the phase has
    no configured effort. Models that don't support reasoning ignore this.
    """
    effort = PHASE_REASONING_EFFORT.get(phase)
    if not effort:
        return None
    return {"reasoning": {"effort": effort}}
