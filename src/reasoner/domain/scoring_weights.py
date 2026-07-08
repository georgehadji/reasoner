"""Domain value objects for utility scoring weights (ACR Phase 3).

These weights control the relative importance of different factors
when computing the utility score U(model, task) for model selection.

Tier presets shift the balance:
  - Budget presets: cost and latency matter more
  - Premium presets: quality (capability match + history) matters more
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringWeights:
    """Tunable weights for the utility function.

    U(m, t) = α · capability_match(m, t)
            + β · quality_history(m, t.role)
            + γ · reliability(m)
            - δ · cost_normalized(m)
            - ε · latency_normalized(m)
    """

    capability: float = 0.35       # α — how well model capabilities match task needs
    quality_history: float = 0.30  # β — past performance for this role (critique scores, success rate)
    reliability: float = 0.15      # γ — circuit breaker state, fallback rate, uptime
    cost_penalty: float = 0.10     # δ — normalized cost penalty (higher = more cost-averse)
    latency_penalty: float = 0.10  # ε — normalized latency penalty (higher = more latency-averse)


# ── Tier Presets ──

BUDGET_WEIGHTS = ScoringWeights(
    capability=0.20,
    quality_history=0.20,
    reliability=0.15,
    cost_penalty=0.25,
    latency_penalty=0.20,
)
"""Budget tier: cost and latency matter most (45% combined)."""

BALANCED_WEIGHTS = ScoringWeights(
    capability=0.35,
    quality_history=0.30,
    reliability=0.15,
    cost_penalty=0.10,
    latency_penalty=0.10,
)
"""Balanced tier: capability match and quality matter more."""

PREMIUM_WEIGHTS = ScoringWeights(
    capability=0.35,
    quality_history=0.35,
    reliability=0.15,
    cost_penalty=0.08,
    latency_penalty=0.07,
)
"""Premium tier: quality dominates, cost and latency are secondary."""


def get_weights_for_tier(tier: str) -> ScoringWeights:
    """Get appropriate scoring weights for a preset tier name.

    Args:
        tier: ``"budget"``, ``"balanced"``, or ``"premium"`` (case-insensitive).
              Unknown tiers default to ``BALANCED_WEIGHTS``.

    Returns:
        The corresponding ``ScoringWeights`` instance.
    """
    tier_map = {
        "budget": BUDGET_WEIGHTS,
        "balanced": BALANCED_WEIGHTS,
        "premium": PREMIUM_WEIGHTS,
    }
    return tier_map.get(tier.lower(), BALANCED_WEIGHTS)


__all__ = [
    "ScoringWeights",
    "BUDGET_WEIGHTS",
    "BALANCED_WEIGHTS",
    "PREMIUM_WEIGHTS",
    "get_weights_for_tier",
]
