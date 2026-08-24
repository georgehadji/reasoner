"""Constraint: max 60% of roles from one lab (configurable)."""

from __future__ import annotations

from collections import Counter

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
)
from reasoner.infrastructure.llm.registry import _vendor_of

# Default: no single vendor can hold more than this fraction of roles
_DEFAULT_MAX_VENDOR_SHARE = 0.60


class NoRepeatLabConstraint:
    """Ensure no single vendor/lab dominates the model assignment.

    This prevents over-reliance on a single provider, which could
    introduce systemic bias or create a single point of failure.
    """

    def __init__(self, max_vendor_share: float = _DEFAULT_MAX_VENDOR_SHARE) -> None:
        self.max_vendor_share = max_vendor_share

    def validate(
        self,
        proposed: dict[str, str],
        preset_id: str,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []

        if not proposed or len(proposed) <= 2:
            return violations

        # Count roles per vendor
        vendor_counts: Counter[str] = Counter()
        for _role, model_id in proposed.items():
            vendor = _vendor_of(model_id)
            vendor_counts[vendor] += 1

        total = len(proposed)
        for vendor, count in vendor_counts.items():
            share = count / total
            if share > self.max_vendor_share:
                # Find the roles assigned to this vendor
                vendor_roles = [
                    r for r, m in proposed.items()
                    if _vendor_of(m) == vendor
                ]
                violations.append(ConstraintViolation(
                    constraint_name="no_repeat_lab",
                    role=vendor_roles[0],
                    model_id=proposed[vendor_roles[0]],
                    reason=(
                        f"Vendor '{vendor}' holds {count}/{total} roles "
                        f"({share:.0%}), exceeding max share of "
                        f"{self.max_vendor_share:.0%}: "
                        f"{', '.join(vendor_roles)}"
                    ),
                    severity="soft",
                ))

        return violations


__all__ = ["NoRepeatLabConstraint"]
