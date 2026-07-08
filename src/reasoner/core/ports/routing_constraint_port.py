"""ACR routing constraint port (Phase 4).

Defines the protocol for routing constraints that can accept or reject
a role → model assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConstraintViolation:
    """Details of a constraint violation found during model selection."""

    constraint_name: str
    role: str
    model_id: str
    reason: str
    severity: Literal["hard", "soft"]  # hard = must fix, soft = warning


@runtime_checkable
class RoutingConstraintPort(Protocol):
    """A constraint that can accept or reject a role→model assignment."""

    def validate(
        self,
        proposed: dict[str, str],  # role → model_id
        preset_id: str,
    ) -> list[ConstraintViolation]:
        """Check the proposed role→model assignment against this constraint.

        Returns:
            A list of violations. Empty list = assignment is valid.
        """
        ...


__all__ = [
    "ConstraintViolation",
    "RoutingConstraintPort",
]
