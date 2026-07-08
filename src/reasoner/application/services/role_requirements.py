"""Default role requirement vectors for ACR (ACR Phase 3).

Defines what capability weights each pipeline role needs.
These are the default values used by the UtilityScorer when no
custom requirements are provided.
"""

from __future__ import annotations

from reasoner.domain.task_requirements import TaskConstraints, TaskRequirement

# ── Role Requirements ─────────────────────────────────────────────────────────

# Each entry maps a role name → TaskRequirement with capability weights
# and hard constraints.
#
# Capability dimensions:
#   reasoning       — multi-step logical inference, puzzle solving
#   creativity      — novel idea generation, divergent thinking
#   critical_thinking — argument analysis, fallacy detection
#   writing         — prose composition, clarity, style
#   coding          — code generation and review
#   consistency     — same output for same input, low variance
#   long_context    — handling large token windows, needle-in-haystack
#   json_output     — structured output compliance
#   knowledge       — factual recall, domain expertise

_ROLE_REQUIREMENTS: dict[str, TaskRequirement] = {
    # ── Perspective generation (Phase 2) ──
    "constructive": TaskRequirement(
        role="constructive",
        capability_weights={"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "destructive": TaskRequirement(
        role="destructive",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "systemic": TaskRequirement(
        role="systemic",
        capability_weights={"reasoning": 0.8, "long_context": 0.7, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "minimalist": TaskRequirement(
        role="minimalist",
        capability_weights={"reasoning": 0.6, "creativity": 0.3, "writing": 0.4},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "empirical": TaskRequirement(
        role="empirical",
        capability_weights={"reasoning": 0.9, "knowledge": 0.8, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "financial": TaskRequirement(
        role="financial",
        capability_weights={"reasoning": 0.85, "knowledge": 0.8, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "environmental": TaskRequirement(
        role="environmental",
        capability_weights={"reasoning": 0.75, "knowledge": 0.8, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "ethical": TaskRequirement(
        role="ethical",
        capability_weights={"reasoning": 0.8, "critical_thinking": 0.9, "writing": 0.7},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "technical": TaskRequirement(
        role="technical",
        capability_weights={"reasoning": 0.9, "coding": 0.7, "writing": 0.4},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "practical": TaskRequirement(
        role="practical",
        capability_weights={"reasoning": 0.7, "knowledge": 0.6, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Debate phases ──
    "opening": TaskRequirement(
        role="opening",
        capability_weights={"reasoning": 0.8, "writing": 0.8, "creativity": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "rebuttal": TaskRequirement(
        role="rebuttal",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "judge": TaskRequirement(
        role="judge",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "writing": 0.7},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Jury phases ──
    "generator": TaskRequirement(
        role="generator",
        capability_weights={"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "critic": TaskRequirement(
        role="critic",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "verifier": TaskRequirement(
        role="verifier",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "json_output": 0.7},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Scoring (Phase 3) ──
    "scoring": TaskRequirement(
        role="scoring",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "json_output": 0.8},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Stress testing (Phase 4) ──
    "stress_test_optimal": TaskRequirement(
        role="stress_test_optimal",
        capability_weights={"reasoning": 0.8, "creativity": 0.6, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "stress_test_constraint": TaskRequirement(
        role="stress_test_constraint",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.8, "writing": 0.4},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "stress_test_adversarial": TaskRequirement(
        role="stress_test_adversarial",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "creativity": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Synthesis (Phase 5) ──
    "synthesis": TaskRequirement(
        role="synthesis",
        capability_weights={"reasoning": 0.9, "writing": 0.9, "long_context": 0.7},
        constraints=TaskConstraints(min_context_tokens=32_000),
    ),
    # ── Classification (Phase 0) ──
    "classification": TaskRequirement(
        role="classification",
        capability_weights={"reasoning": 0.6, "consistency": 0.7, "json_output": 0.8},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Decomposition (Phase 1) ──
    "decomposition": TaskRequirement(
        role="decomposition",
        capability_weights={"reasoning": 0.85, "long_context": 0.6, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Enhancement sub-agents ──
    "context_enrichment": TaskRequirement(
        role="context_enrichment",
        capability_weights={"reasoning": 0.7, "knowledge": 0.8, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "ambiguity_detection": TaskRequirement(
        role="ambiguity_detection",
        capability_weights={"reasoning": 0.8, "critical_thinking": 0.8, "json_output": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "scope_narrowing": TaskRequirement(
        role="scope_narrowing",
        capability_weights={"reasoning": 0.8, "writing": 0.5, "consistency": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Research ──
    "research_query": TaskRequirement(
        role="research_query",
        capability_weights={"reasoning": 0.6, "knowledge": 0.5, "json_output": 0.7},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "research_synthesis": TaskRequirement(
        role="research_synthesis",
        capability_weights={"reasoning": 0.8, "writing": 0.8, "long_context": 0.7},
        constraints=TaskConstraints(min_context_tokens=32_000),
    ),
}

# ── Catch-all Fallback ──

_DEFAULT_REQUIREMENT = TaskRequirement(
    role="unknown",
    capability_weights={"reasoning": 0.5, "writing": 0.5},
    constraints=TaskConstraints(),
)


def get_requirement(role: str) -> TaskRequirement:
    """Get the task requirement for a role, or a sensible default.

    Args:
        role: The pipeline role name (e.g. ``"constructive"``, ``"scoring"``).

    Returns:
        The corresponding ``TaskRequirement``, or a default if the role
        is not in the registry.
    """
    return _ROLE_REQUIREMENTS.get(role, _DEFAULT_REQUIREMENT)


def get_all_requirements() -> dict[str, TaskRequirement]:
    """Return all registered role requirements."""
    return dict(_ROLE_REQUIREMENTS)


__all__ = [
    "get_requirement",
    "get_all_requirements",
]
