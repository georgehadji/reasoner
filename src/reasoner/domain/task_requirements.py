"""Domain value objects for task requirements (ACR Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskConstraints:
    """Hard filters — a model must satisfy ALL to be eligible for a role.

    These are checked BEFORE capability ranking. Models failing any
    constraint are excluded entirely from consideration.
    """

    min_context_tokens: int = 0
    max_cost_per_1k_output_usd: float = float("inf")
    max_latency_p95_ms: float = float("inf")
    requires_tools: bool = False
    requires_vision: bool = False
    requires_temperature: bool = True  # Excludes o-series by default
    excluded_blocs: frozenset[str] = field(default_factory=frozenset)
    excluded_models: frozenset[str] = field(default_factory=frozenset)
    # Minimum measured resistance to self-propagating content, 0.0-1.0. Only
    # meaningful for terminal roles (synthesis, verification) whose output is
    # persisted, replayed as recalled memory, or shown to the user as the answer.
    # 0.0 = no requirement. See infrastructure/llm/propagation_resistance.py for
    # why this is a measured table rather than a capability heuristic.
    min_propagation_resistance: float = 0.0


@dataclass(frozen=True)
class TaskRequirement:
    """What a pipeline role needs — capability weights + hard constraints.

    This is the primary input to the utility scorer, which computes
    ``U(model, requirement)`` for each candidate model.
    """

    role: str  # e.g. "constructive", "scoring", "synthesis"
    capability_weights: dict[str, float] = field(default_factory=dict)
    # e.g. {"reasoning": 0.8, "creativity": 0.6}
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    priority: float = 1.0  # Higher = more important to get right


__all__ = [
    "TaskConstraints",
    "TaskRequirement",
]
