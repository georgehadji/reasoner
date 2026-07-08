"""Constraint: avoid models near their concurrency limit."""

from __future__ import annotations

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
    RoutingConstraintPort,
)

# Threshold: warn when concurrency usage exceeds this fraction
_CONCURRENCY_WARN_THRESHOLD = 0.85

# Threshold: reject when concurrency usage exceeds this fraction
_CONCURRENCY_HARD_THRESHOLD = 0.95


class ConcurrencyConstraint:
    """Avoid models near their rate-limit concurrency ceiling."""

    def validate(
        self,
        proposed: dict[str, str],
        preset_id: str,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []

        if not proposed:
            return violations

        for role, model_id in proposed.items():
            usage_ratio = self._get_concurrency_usage(model_id)
            if usage_ratio >= _CONCURRENCY_HARD_THRESHOLD:
                violations.append(ConstraintViolation(
                    constraint_name="concurrency",
                    role=role,
                    model_id=model_id,
                    reason=(
                        f"Concurrency usage at {usage_ratio:.0%} "
                        f"(exceeds hard threshold of {_CONCURRENCY_HARD_THRESHOLD:.0%})"
                    ),
                    severity="hard",
                ))
            elif usage_ratio >= _CONCURRENCY_WARN_THRESHOLD:
                violations.append(ConstraintViolation(
                    constraint_name="concurrency",
                    role=role,
                    model_id=model_id,
                    reason=(
                        f"Concurrency usage at {usage_ratio:.0%} "
                        f"(approaching limit)"
                    ),
                    severity="soft",
                ))

        return violations

    def _get_concurrency_usage(self, model_id: str) -> float:
        """Get the current concurrency usage for a model.

        Returns 0.0 (no usage) if data unavailable.
        """
        try:
            from reasoner.infrastructure.llm.router import (
                _get_llm_semaphore, _get_model_limit,
            )
            sem = _get_llm_semaphore(model_id)
            limit = _get_model_limit(model_id)
            if limit <= 0:
                return 0.0
            # Estimate: semaphore._value is remaining permits
            used = limit - sem._value
            return used / limit
        except Exception:
            return 0.0


__all__ = ["ConcurrencyConstraint"]
