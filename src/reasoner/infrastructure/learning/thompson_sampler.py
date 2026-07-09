"""Thompson Sampling for Bayesian model selection (ACR Phase 6).

Each (model, role) pair maintains a Beta posterior distribution:
    Beta(α = successes + 1, β = failures + 1)

Thompson Sampling naturally handles:
- **Cold start**: new models have wide posteriors (α=1, β=1) → sampled more often
- **Convergence**: proven models are exploited as posterior narrows
- **Non-stationarity**: a sliding window decays old observations
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BetaPosterior:
    """Beta distribution posterior for a (model, role) pair.

    The posterior is Beta(α, β) where:
      α = sum_of_rewards + 1  (pseudo-count prior)
      β = call_count - sum_of_rewards + 1  (pseudo-count prior)

    Thompson Sampling samples from this distribution; higher samples
    indicate higher expected quality.
    """

    alpha: float = 1.0   # Prior pseudo-count for success
    beta: float = 1.0    # Prior pseudo-count for failure
    call_count: int = 0   # Total observations
    sum_rewards: float = 0.0  # Cumulative reward (0.0–1.0 per call)

    @property
    def mean(self) -> float:
        """Expected value of the Beta distribution."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def std(self) -> float:
        """Standard deviation — uncertainty measure."""
        total = self.alpha + self.beta
        if total <= 2:
            return 1.0
        return math.sqrt(
            (self.alpha * self.beta) / (total * total * (total + 1))
        )

    @property
    def sample_count(self) -> int:
        """Number of observations contributing to this posterior."""
        return self.call_count

    def update(self, reward: float) -> None:
        """Update the posterior with a new reward observation.

        Reward is treated as a fractional success count:
          reward=1.0 → α += 1
          reward=0.0 → β += 1
          reward=0.7 → α += 0.7, β += 0.3
        """
        if not (0.0 <= reward <= 1.0):
            reward = max(0.0, min(1.0, reward))

        self.alpha += reward
        self.beta += 1.0 - reward
        self.call_count += 1
        self.sum_rewards += reward

    def decay(self, factor: float = 0.95) -> None:
        """Apply exponential decay to move posterior toward the prior.

        Scales alpha and beta by ``factor``, reducing the influence of
        older observations. This handles non-stationarity by letting
        the model adapt to changing performance over time.

        Example: ``decay(0.95)`` applied daily reduces the weight of
        30-day-old data to ``0.95^30 ≈ 0.21`` of its original weight.

        The prior (α=1, β=1) is preserved so the posterior always
        maintains at least the prior's strength.
        """
        self.alpha = 1.0 + (self.alpha - 1.0) * factor
        self.beta = 1.0 + (self.beta - 1.0) * factor

    def sample(self) -> float:
        """Draw a sample from the Beta posterior.

        Returns a value in [0, 1]. New models (α=1, β=1) produce
        uniform random samples. Converged models produce samples
        tightly clustered around the mean.
        """
        # Beta distribution via Gamma variates
        try:
            x = random.gammavariate(self.alpha, 1.0)
            y = random.gammavariate(self.beta, 1.0)
            return x / (x + y)
        except (ValueError, ZeroDivisionError):
            return self.mean


class ThompsonSampler:
    """Bayesian model selection with explore/exploit balance.

    Maintains Beta posteriors per (model_id, role) pair.
    Selection samples from each model's posterior; higher samples = better.
    """

    def __init__(self) -> None:
        self._posteriors: dict[tuple[str, str], BetaPosterior] = {}

    def get_posterior(self, model_id: str, role: str) -> BetaPosterior:
        """Get or create the Beta posterior for a (model, role) pair."""
        key = (model_id, role)
        if key not in self._posteriors:
            self._posteriors[key] = BetaPosterior()
        return self._posteriors[key]

    def update(self, model_id: str, role: str, reward: float) -> None:
        """Update the posterior for (model, role) with a reward."""
        posterior = self.get_posterior(model_id, role)
        posterior.update(reward)

    def select_model(self, candidates: list[str], role: str) -> str | None:
        """Select the best model among candidates using Thompson Sampling.

        Draws one sample from each model's posterior for the given role
        and returns the model with the highest sample.

        Args:
            candidates: List of model IDs to choose from.
            role: The pipeline role.

        Returns:
            The selected model ID, or None if candidates is empty.
        """
        if not candidates:
            return None

        best_model = candidates[0]
        best_sample = -1.0

        for model_id in candidates:
            posterior = self.get_posterior(model_id, role)
            sample_val = posterior.sample()
            if sample_val > best_sample:
                best_sample = sample_val
                best_model = model_id

        return best_model

    def export_capabilities(self, min_samples: int = 5) -> dict[str, dict[str, float]]:
        """Export model capability scores from posteriors.

        Converts each posterior mean into a capability score.
        Only models with at least ``min_samples`` observations are exported.

        Returns:
            dict mapping model_id → {role: mean_score, ...}
        """
        result: dict[str, dict[str, float]] = {}
        for (model_id, role), posterior in self._posteriors.items():
            if posterior.call_count < min_samples:
                continue
            if model_id not in result:
                result[model_id] = {}
            result[model_id][role] = posterior.mean
        return result

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics for observability."""
        total_pairs = len(self._posteriors)
        total_observations = sum(p.call_count for p in self._posteriors.values())
        models = len(set(k[0] for k in self._posteriors))
        roles = len(set(k[1] for k in self._posteriors))

        return {
            "model_role_pairs": total_pairs,
            "total_observations": total_observations,
            "unique_models": models,
            "unique_roles": roles,
        }


__all__ = ["BetaPosterior", "ThompsonSampler"]
