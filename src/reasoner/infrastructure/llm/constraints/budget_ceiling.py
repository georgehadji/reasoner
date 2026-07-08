"""Constraint: total estimated cost ≤ preset tier budget."""

from __future__ import annotations

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
    RoutingConstraintPort,
)

# Estimated per-call cost ceilings by preset tier (USD)
_TIER_BUDGET_CEILINGS: dict[str, float] = {
    "budget": 0.05,      # $0.05 max per call
    "balanced": 0.15,    # $0.15 max per call
    "premium": 0.50,     # $0.50 max per call
}

# Default fallback for unknown tiers
_DEFAULT_BUDGET_CEILING = 0.15


def _infer_tier(preset_id: str) -> str:
    """Extract the tier from a preset ID like 'multi-perspective-budget'."""
    for tier in ("premium", "balanced", "budget"):
        if tier in preset_id.lower():
            return tier
    return "balanced"


class BudgetCeilingConstraint:
    """Ensure each model's estimated cost stays within preset tier budget."""

    def validate(
        self,
        proposed: dict[str, str],
        preset_id: str,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []

        if not proposed:
            return violations

        tier = _infer_tier(preset_id)
        ceiling = _TIER_BUDGET_CEILINGS.get(tier, _DEFAULT_BUDGET_CEILING)

        # Check each assigned model against the ceiling
        for role, model_id in proposed.items():
            # Estimate cost from model constraints
            estimated_cost = self._estimate_model_cost(model_id)
            if estimated_cost > ceiling:
                violations.append(ConstraintViolation(
                    constraint_name="budget_ceiling",
                    role=role,
                    model_id=model_id,
                    reason=(
                        f"Estimated cost ${estimated_cost:.4f} exceeds "
                        f"tier '{tier}' ceiling of ${ceiling:.4f}"
                    ),
                    severity="hard",
                ))

        return violations

    def _estimate_model_cost(self, model_id: str) -> float:
        """Estimate the per-call cost for a model based on its ID.

        Uses the cost hints from the capability registry (Phase 2).
        Falls back to cheap default for unknown models.
        """
        from reasoner.infrastructure.llm.capability_registry import (
            _build_constraints,
        )
        try:
            constraints = _build_constraints(model_id)
            # Estimate: 2000 input + 1000 output tokens
            cost = (
                constraints.cost_per_1k_input_usd * 2
                + constraints.cost_per_1k_output_usd * 1
            )
            return cost
        except Exception:
            return 0.001  # Cheap default for unknown models


__all__ = ["BudgetCeilingConstraint"]
