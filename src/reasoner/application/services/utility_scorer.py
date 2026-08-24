"""Utility scorer for adaptive model selection (ACR Phase 3).

Computes U(model, task) = α·capability_match + β·quality_history
                         + γ·reliability - δ·cost - ε·latency

Uses weighted dot product for capability matching — NOT cosine similarity.
"""

from __future__ import annotations

import math

from reasoner.domain.model_capabilities import ModelProfile
from reasoner.domain.scoring_weights import (
    BALANCED_WEIGHTS,
    ScoringWeights,
)
from reasoner.domain.task_requirements import TaskRequirement

COLD_START_SCORE = 0.5
"""Score returned for a model with no measured capabilities.

Callers must treat a score equal to this as "no evidence", not as a passing
grade — every unbenchmarked model returns exactly this value, so comparing
against it decides nothing.
"""


class UtilityScorer:
    """Computes utility U(model, task) for model selection.

    The utility function blends:
    - Capability match (weighted dot product of task weights × model scores)
    - Quality history (past critique scores / success rate from telemetry)
    - Reliability (circuit breaker state, fallback rate)
    - Cost penalty (normalized model cost)
    - Latency penalty (normalized model latency)

    Higher scores = better model-task fit.
    """

    def __init__(
        self,
        weights: ScoringWeights | None = None,
    ) -> None:
        """Initialise the scorer.

        Args:
            weights: Scoring weights. Defaults to balanced weights if None.
        """
        self.weights = weights or BALANCED_WEIGHTS

    def score(self, model: ModelProfile, requirement: TaskRequirement) -> float:
        """Compute the utility score for a model on a task.

        Returns a value in [0.0, 1.0] where higher is better.
        """
        if not model.has_capabilities:
            # Cold start: neutral score — new models get exploration budget
            return COLD_START_SCORE

        w = self.weights
        caps = model.capabilities
        assert caps is not None  # checked above

        capability_score = self._capability_match(
            caps.scores, requirement.capability_weights
        )
        quality_score = self._quality_history(caps.scores, requirement)
        reliability_score = self._reliability_score(model)
        cost_penalty = self._cost_penalty(model)
        latency_penalty = self._latency_penalty(model)

        utility = (
            w.capability * capability_score
            + w.quality_history * quality_score
            + w.reliability * reliability_score
            - w.cost_penalty * cost_penalty
            - w.latency_penalty * latency_penalty
        )

        # Clamp to [0, 1]
        return max(0.0, min(1.0, utility))

    def rank_models(
        self,
        candidates: list[ModelProfile],
        requirement: TaskRequirement,
        top_k: int | None = None,
    ) -> list[tuple[ModelProfile, float]]:
        """Rank candidate models by utility score for a given task requirement.

        Args:
            candidates: List of eligible model profiles (pre-filtered by constraints).
            requirement: The task requirement to score against.
            top_k: Optional limit on the number of results.

        Returns:
            List of (model, score) tuples sorted in descending order of score.
        """
        scored = [(m, self.score(m, requirement)) for m in candidates]
        scored.sort(key=lambda x: (-x[1], x[0].model_id))

        if top_k is not None:
            return scored[:top_k]
        return scored

    # ── Component Scores ──────────────────────────────────────────────────

    def _capability_match(
        self,
        model_scores: dict[str, float],
        task_weights: dict[str, float],
    ) -> float:
        """Weighted dot product of capability scores with task weights.

        Returns 0.0–1.0 normalized value.

        Design note: Weighted dot product is used instead of cosine similarity
        because cosine similarity measures directional alignment regardless of
        magnitude — a model scoring 0.3 on everything would have perfect cosine
        similarity with any uniform requirement vector, despite being mediocre.
        Weighted dot product penalizes low absolute scores on important dimensions.
        """
        if not task_weights:
            return 0.5  # No requirement = neutral score

        total_weight = sum(task_weights.values())
        if total_weight == 0:
            return 0.5

        score = sum(
            weight * model_scores.get(dim, 0.0)
            for dim, weight in task_weights.items()
        )
        return score / total_weight  # Normalize to [0, 1]

    def _quality_history(
        self,
        model_scores: dict[str, float],
        requirement: TaskRequirement,
    ) -> float:
        """Quality history score based on past performance.

        Uses the ``consistency`` and ``reasoning`` scores as proxies for
        historical quality when per-role telemetry isn't available yet.
        With telemetry (Phase 6), this will use actual critique scores.
        """
        # Default: use model's consistency score as quality proxy
        consistency = model_scores.get("consistency", 0.5)
        reasoning = model_scores.get("reasoning", 0.5)

        # Blend: if we have role-specific telemetry, it overrides
        return 0.6 * consistency + 0.4 * reasoning

    def _reliability_score(self, model: ModelProfile) -> float:
        """Reliability score based on circuit breaker and fallback behavior.

        Returns 1.0 for fully reliable, 0.0 for untrusted.
        Currently returns neutral 0.8 — Phase 6 will use actual
        circuit breaker state when the learning engine is integrated.
        """
        # Placeholder: Phase 6 will integrate circuit breaker state here
        return 0.8

    def _cost_penalty(self, model: ModelProfile) -> float:
        """Normalized cost penalty based on per-1K-token cost.

        Uses a logarithmic scale so cost differences don't dominate.
        Returns 0.0 (cheapest) to 1.0 (most expensive).
        """
        cost = model.cost_per_1k_total_usd
        if cost <= 0.0:
            return 0.0

        # Log scale: $0.001 → 0.25, $0.01 → 0.50, $0.10 → 0.75, $1.00 → 1.0
        return min(1.0, math.log10(1 + cost * 1000) / 3.0)

    def _latency_penalty(self, model: ModelProfile) -> float:
        """Normalized latency penalty.

        Currently returns a neutral score. Will use real latency
        telemetry once Phase 1 has collected sufficient data.
        """
        # Placeholder: Phase 5+ will use p95 latency from telemetry
        return 0.3  # Moderate default penalty


__all__ = ["UtilityScorer"]
