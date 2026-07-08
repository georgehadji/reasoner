"""Exploration budget policy for online learning (ACR Phase 6).

Controls how much exploration vs exploitation is performed.

- Budget presets: 15% explore (users accept cost-optimized routing)
- Premium presets: 5% explore (users paying more get less experimentation)
- Benchmark warmup: minimum calls before model enters adaptive pool

Thompson Sampling naturally reduces exploration as posterior narrows.
This policy provides a hard floor to ensure minimum exploration.
"""

from __future__ import annotations

import math
import random


# Default exploration rates by preset tier
_EXPLORATION_RATES: dict[str, float] = {
    "budget": 0.15,      # 15% explore — cost-optimized users accept more experimentation
    "balanced": 0.10,    # 10% explore — default
    "premium": 0.05,     # 5% explore — paying users get less experimentation
}

# Default warmup threshold (number of calls before model enters adaptive pool)
_DEFAULT_WARMUP_CALLS = 50


class ExplorationPolicy:
    """Controls how much exploration vs exploitation.

    The policy has two layers:
    1. **Hard floor**: enforced minimum exploration rate per tier
    2. **Warmup gate**: models with fewer than ``warmup_calls`` observations
       are always explored (cold start)

    Combined with Thompson Sampling's natural explore/exploit balance,
    this ensures sufficient exploration without wasting budget.
    """

    def __init__(
        self,
        tier: str = "balanced",
        exploration_rate: float | None = None,
        warmup_calls: int = _DEFAULT_WARMUP_CALLS,
    ) -> None:
        """Initialise the exploration policy.

        Args:
            tier: Preset tier — ``"budget"``, ``"balanced"``, or ``"premium"``.
            exploration_rate: Override the default rate for the tier.
                If None, uses the tier's default rate.
            warmup_calls: Minimum observations before model enters adaptive pool.
        """
        self.tier = tier
        self.exploration_rate = (
            exploration_rate if exploration_rate is not None
            else _EXPLORATION_RATES.get(tier, 0.10)
        )
        self.warmup_calls = warmup_calls

    def should_explore(self) -> bool:
        """Decide whether to explore (vs exploit) on this selection.

        Returns True with probability = exploration_rate.
        """
        return random.random() < self.exploration_rate

    def is_warmed_up(self, call_count: int) -> bool:
        """Check if a model has enough observations to enter the adaptive pool.

        Models below the warmup threshold should always be explored
        (cold start).
        """
        return call_count >= self.warmup_calls

    def get_effective_rate(self, model_call_count: int) -> float:
        """Get the effective exploration rate for a model.

        Cold-start models (below warmup threshold) always explore (1.0 rate).
        Warmed-up models use the tier's configured exploration rate.
        """
        if not self.is_warmed_up(model_call_count):
            return 1.0  # Always explore cold-start models
        return self.exploration_rate

    def get_stats(self) -> dict[str, float | str | int]:
        """Return statistics for observability."""
        return {
            "tier": self.tier,
            "exploration_rate": self.exploration_rate,
            "warmup_calls": self.warmup_calls,
        }


__all__ = ["ExplorationPolicy"]
