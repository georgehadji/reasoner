"""Constraint: skip models with open circuit breakers."""

from __future__ import annotations

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
)


class CircuitStateConstraint:
    """Skip models whose circuit breaker is in the OPEN state."""

    def validate(
        self,
        proposed: dict[str, str],
        preset_id: str,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []

        if not proposed:
            return violations

        for role, model_id in proposed.items():
            circuit_state = self._get_circuit_state(model_id)
            if circuit_state == "open":
                violations.append(ConstraintViolation(
                    constraint_name="circuit_state",
                    role=role,
                    model_id=model_id,
                    reason=f"Circuit breaker is OPEN for {model_id}",
                    severity="hard",
                ))
            elif circuit_state == "half_open":
                violations.append(ConstraintViolation(
                    constraint_name="circuit_state",
                    role=role,
                    model_id=model_id,
                    reason=f"Circuit breaker is HALF_OPEN for {model_id}",
                    severity="soft",
                ))

        return violations

    def _get_circuit_state(self, model_id: str) -> str:
        """Get the circuit breaker state for a model.

        Returns ``"closed"`` if no circuit breaker is registered (no data
        yet means assume healthy).
        """
        try:
            from reasoner.circuit_breaker import get_circuit_breaker
            cb = get_circuit_breaker(f"llm:{model_id}")
            return cb.state if hasattr(cb, "state") else "closed"
        except Exception:
            return "closed"


__all__ = ["CircuitStateConstraint"]
