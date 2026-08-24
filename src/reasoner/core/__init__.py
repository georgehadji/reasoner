"""
core — shared abstractions for the Reasoner pipeline.

Imports:
    from reasoner.core import Phase, PhaseResult, PhaseConfig, make_phase_result
    from reasoner.core import PerspectiveDefinition, DEFAULT_PERSPECTIVES, PERSPECTIVES_BY_NAME
"""

from reasoner.core.perspectives import (
    DEFAULT_PERSPECTIVES,
    PERSPECTIVES_BY_NAME,
    PerspectiveDefinition,
)
from reasoner.core.protocol import Phase, PhaseConfig, PhaseResult, make_phase_result

__all__ = [
    "Phase",
    "PhaseConfig",
    "PhaseResult",
    "make_phase_result",
    "PerspectiveDefinition",
    "DEFAULT_PERSPECTIVES",
    "PERSPECTIVES_BY_NAME",
]
