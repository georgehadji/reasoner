"""ACR routing constraints (Phase 4).

Constraint implementations that validate model assignments against
hard invariants (bloc diversity, budget ceiling, circuit state).
"""

from __future__ import annotations

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
    RoutingConstraintPort,
)
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

__all__ = [
    "ConstraintViolation",
    "RoutingConstraintPort",
    "BlocDiversityConstraint",
    "BudgetCeilingConstraint",
    "CircuitStateConstraint",
    "ConcurrencyConstraint",
    "NoRepeatLabConstraint",
]
