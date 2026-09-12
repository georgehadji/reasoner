"""Phase sequence registry and dispatcher for reasoning methods."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from reasoner.domain.pipeline_state import PipelineState


class PhaseFn(Protocol):
    async def __call__(self, state: PipelineState) -> Any: ...

@dataclass(frozen=True)
class PhaseStep:
    """A single step in a pipeline phase sequence."""

    num: int | float
    name: str
    fn: PhaseFn
    serializer: Callable[[PipelineState], dict]
    critical: bool = False


class PipelineFlow:
    """Registry that maps method names to ordered phase sequences."""

    def __init__(self) -> None:
        self._sequences: dict[str, list[PhaseStep]] = {}

    def register(self, method: str, steps: list[PhaseStep]) -> None:
        """Register a phase sequence for a reasoning method."""
        if method in self._sequences:
            raise ValueError(f"Method '{method}' already registered")
        self._sequences[method] = steps

    def get_sequence(self, method: str) -> list[PhaseStep]:
        """Get the phase sequence for a method (defaults to multi-perspective)."""
        return self._sequences.get(method, self._sequences.get("multi_perspective", []))

    @property
    def methods(self) -> set[str]:
        """Return all registered method names."""
        return set(self._sequences.keys())
