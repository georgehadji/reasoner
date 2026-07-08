"""Quality signal aggregation for online learning (ACR Phase 6).

Converts raw LLM call telemetry into a 0.0–1.0 reward signal
using a weighted blend of available quality signals.

Signal hierarchy (by availability and cost):
1. Completion success — every call, free
2. JSON validity — every call expecting JSON, free
3. Phase-3 critique score — orchestrated pipelines, already computed
4. Stress test pass rate — orchestrated pipelines, already computed
"""

from __future__ import annotations

from reasoner.domain.telemetry import LLMCallTelemetry


class QualitySignalAggregator:
    """Converts raw telemetry into quality scores for learning.

    Computes a composite reward signal from all available quality
    dimensions. Missing signals are silently skipped (weight re-balanced
    among available signals).
    """

    def compute_reward(self, telemetry: LLMCallTelemetry) -> float:
        """Convert a telemetry event into a 0.0–1.0 reward signal.

        Uses the exact weighting scheme from the plan:
        - Success: 30%
        - JSON validity: 15%
        - Critique score: 35%
        - Stress test pass: 20%

        Missing signals are excluded and the weight is re-normalized.
        """
        score = 0.0
        weight_sum = 0.0

        # Always available
        score += 0.3 * (1.0 if telemetry.success else 0.0)
        weight_sum += 0.3

        # JSON validity (when available)
        if telemetry.json_valid is not None:
            score += 0.15 * (1.0 if telemetry.json_valid else 0.0)
            weight_sum += 0.15

        # Phase-specific (when available)
        if telemetry.critique_score is not None:
            score += 0.35 * (telemetry.critique_score / 10.0)
            weight_sum += 0.35

        if telemetry.stress_test_pass is not None:
            score += 0.20 * (1.0 if telemetry.stress_test_pass else 0.0)
            weight_sum += 0.20

        # Normalize: if no signals were available, return neutral 0.5
        return score / weight_sum if weight_sum > 0 else 0.5

    def compute_batch_rewards(
        self,
        events: list[LLMCallTelemetry],
    ) -> list[tuple[str, str, float]]:
        """Compute rewards for a batch of telemetry events.

        Returns:
            List of (model_id, role, reward) tuples.
        """
        results: list[tuple[str, str, float]] = []
        for event in events:
            reward = self.compute_reward(event)
            results.append((event.model_id, event.role, reward))
        return results


__all__ = ["QualitySignalAggregator"]
