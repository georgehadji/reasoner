"""Single source of truth for LLM temperature values across the Reasoner pipeline."""

from __future__ import annotations

# Optimal temperatures per reasoning phase.
# Low  (0.3-0.4) : consistency / structured output (classification, decomposition, critique)
# Mid  (0.5)     : systematic rigor with minor variability (stress testing, synthesis)
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
