"""RegressionGate — pass/fail decision for harness mutation evaluation (#4b).

A mutation passes the gate only if:
  - No solved-case regressions (regressions list is empty)
  - Target metric improves by at least MIN_IMPROVEMENT_DELTA (5%)
  - Cost/safety metrics are not worse than MAX_REGRESSION (2%)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reasoner.core.evolution_constants import (
    EVOLUTION_MAX_REGRESSION,
    EVOLUTION_MIN_IMPROVEMENT_DELTA,
)
from reasoner.domain.harness_metrics import ReplayResult


@dataclass
class GateVerdict:
    """Outcome of a regression gate check."""
    passed: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.passed:
            return "PASS"
        return f"REJECTED: {'; '.join(self.reasons)}"


class RegressionGate:
    """Determines whether a mutation evaluation qualifies for promotion."""

    def check(
        self,
        result: ReplayResult,
        min_improvement: float = EVOLUTION_MIN_IMPROVEMENT_DELTA,
        max_regression: float = EVOLUTION_MAX_REGRESSION,
    ) -> GateVerdict:
        """Evaluate a ReplayResult against the regression gate criteria.

        Args:
            result: ReplayResult from HarnessReplayService.evaluate().
            min_improvement: Minimum delta improvement to qualify (default 5%).
            max_regression: Maximum acceptable cost/safety regression (default 2%).

        Returns:
            GateVerdict with pass/fail and reasons.
        """
        reasons: list[str] = []

        # Criterion 1: No regressions on previously solved cases
        if result.regressions:
            reasons.append(
                f"{len(result.regressions)} regression(s) found: {result.regressions[0]}"
            )

        # Criterion 2: Improvement on the targeted metric
        if result.delta_improvement < min_improvement:
            reasons.append(
                f"Improvement {result.delta_improvement:.1%} below "
                f"threshold {min_improvement:.1%}"
            )

        # Criterion 3: Cost/safety not worse
        cost_delta = result.total_cost_usd_after - result.total_cost_usd_before
        cost_regression = cost_delta / max(result.total_cost_usd_before, 0.001)
        if cost_regression > max_regression:
            reasons.append(
                f"Cost regressed by {cost_regression:.1%} "
                f"(max allowed {max_regression:.1%})"
            )

        return GateVerdict(
            passed=len(reasons) == 0,
            reasons=reasons,
        )
