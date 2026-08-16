"""Constraint resolver — finds the best valid model assignment (ACR Phase 4).

Algorithm:
1. Start with top-utility model for each role
2. Check all constraints
3. If violations exist, try swapping violated roles to next-best models
4. Re-check constraints (max 10 iterations)
5. If no valid assignment found, return fallback assignment
"""

from __future__ import annotations

import copy
from typing import Any

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
    RoutingConstraintPort,
)

# ── Default constraints ──

_DEFAULT_CONSTRAINTS: list[RoutingConstraintPort] = []


def _get_default_constraints() -> list[RoutingConstraintPort]:
    """Lazy-load default constraint instances."""
    if not _DEFAULT_CONSTRAINTS:
        from reasoner.infrastructure.llm.constraints.bloc_diversity import (
            BlocDiversityConstraint,
        )
        from reasoner.infrastructure.llm.constraints.budget_ceiling import (
            BudgetCeilingConstraint,
        )
        from reasoner.infrastructure.llm.constraints.circuit_state import (
            CircuitStateConstraint,
        )
        from reasoner.infrastructure.llm.constraints.concurrency import (
            ConcurrencyConstraint,
        )
        from reasoner.infrastructure.llm.constraints.no_repeat_lab import (
            NoRepeatLabConstraint,
        )
        _DEFAULT_CONSTRAINTS.extend([
            BlocDiversityConstraint(),
            BudgetCeilingConstraint(),
            CircuitStateConstraint(),
            ConcurrencyConstraint(),
            NoRepeatLabConstraint(),
        ])
    return _DEFAULT_CONSTRAINTS


class ConstraintResolver:
    """Applies constraints to ranked model lists, finding the best valid assignment.

    Works with pre-scored model lists for each role. Attempts to find
    a valid assignment that satisfies all constraints while preserving
    as much utility as possible.
    """

    def __init__(
        self,
        constraints: list[RoutingConstraintPort] | None = None,
        max_iterations: int = 10,
    ) -> None:
        """Initialise the resolver.

        Args:
            constraints: List of constraint implementations to check.
                Defaults to all 5 standard constraints.
            max_iterations: Maximum backtracking iterations (default 10).
        """
        self.constraints = constraints or _get_default_constraints()
        self.max_iterations = max_iterations

    def resolve(
        self,
        ranked_per_role: dict[str, list[tuple[str, float]]],
        # role → [(model_id, score), ...] sorted descending
        preset_id: str = "",
        fallback: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Find the best valid assignment that satisfies all constraints.

        Args:
            ranked_per_role: For each role, a list of (model_id, utility_score)
                tuples sorted in descending score order.
            preset_id: The preset ID for constraint checking.
            fallback: Fallback assignment (role → model_id) used if no valid
                assignment can be found. Often the static preset routing.

        Returns:
            role → model_id assignment that satisfies all constraints.
            Falls back to the provided fallback or the top choices.
        """
        # 1. Start with top choice for each role
        assignment: dict[str, str] = {}
        for role, ranked in ranked_per_role.items():
            assignment[role] = ranked[0][0] if ranked else ""

        # 2. Iteratively fix violations
        for _iteration in range(self.max_iterations):
            violations = self._check_all(assignment, preset_id)
            hard_violations = [v for v in violations if v.severity == "hard"]

            if not hard_violations:
                # Valid assignment found
                return assignment

            # Try to fix the first hard violation
            fixed = self._fix_violation(
                hard_violations[0], assignment, ranked_per_role
            )
            if not fixed:
                # Can't fix — use fallback or best effort
                return fallback or dict(assignment)

            assignment = fixed

        # Exhausted iterations — use fallback or best effort
        return fallback or assignment

    def _check_all(
        self,
        assignment: dict[str, str],
        preset_id: str,
    ) -> list[ConstraintViolation]:
        """Check all constraints against the current assignment."""
        all_violations: list[ConstraintViolation] = []
        for constraint in self.constraints:
            try:
                violations = constraint.validate(assignment, preset_id)
                all_violations.extend(violations)
            except Exception:
                pass
        return all_violations

    def _fix_violation(
        self,
        violation: ConstraintViolation,
        current: dict[str, str],
        ranked_per_role: dict[str, list[tuple[str, float]]],
    ) -> dict[str, str] | None:
        """Try to fix a constraint violation by picking the next-best model.

        Returns the updated assignment or None if no fix is possible.
        """
        role = violation.role
        if role not in ranked_per_role or not ranked_per_role[role]:
            return None

        ranked = ranked_per_role[role]
        current_model = current.get(role, "")

        # Find the next-best model that differs from the current one
        for model_id, _score in ranked:
            if model_id != current_model:
                new_assignment = dict(current)
                new_assignment[role] = model_id
                # Re-check: does this fix the violation?
                new_violations = self._check_all(new_assignment, "")
                if not any(
                    v.constraint_name == violation.constraint_name
                    and v.severity == "hard"
                    for v in new_violations
                ):
                    return new_assignment

        # No suitable alternative found
        return None


__all__ = ["ConstraintResolver"]
