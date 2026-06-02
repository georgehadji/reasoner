"""Phase sequence registry and dispatcher for reasoning methods."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Protocol

from reasoner.domain.pipeline_state import PipelineState


class PhaseFn(Protocol):
    async def __call__(self, state: PipelineState) -> None: ...


@dataclass(frozen=True)
class PhaseStep:
    """A single step in a pipeline phase sequence."""

    num: int | float
    name: str
    fn: PhaseFn
    serializer: Callable[[PipelineState], dict]
    critical: bool = False
    depends_on: list[str] = field(default_factory=list)


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


async def execute_phases_dag(
    phases: list[PhaseStep],
    state: PipelineState,
    run_phase_fn: Callable[[PhaseFn, PipelineState], None],
) -> None:
    """Execute phases respecting dependencies. Independent phases run in parallel.

    Args:
        phases: Ordered list of PhaseStep definitions.
        state: Shared PipelineState mutated by each phase.
        run_phase_fn: Callable that actually executes a single phase function
            against the state (e.g. wraps keepalive, timeout, SSE emission).

    Raises:
        RuntimeError: If a circular dependency is detected.
    """
    completed: set[str] = set()
    pending = list(phases)

    while pending:
        # Find all phases whose dependencies are satisfied
        ready = [
            p for p in pending
            if all(dep in completed for dep in p.depends_on)
        ]
        if not ready:
            raise RuntimeError(
                f"Circular dependency detected among: {[p.name for p in pending]}"
            )

        # Remove ready phases from pending
        for p in ready:
            pending.remove(p)

        # Execute ready phases in parallel
        async def _run_step(step: PhaseStep) -> str:
            await run_phase_fn(step.fn, state)
            return step.name

        results = await asyncio.gather(
            *[_run_step(s) for s in ready], return_exceptions=True
        )
        for name, result in zip([s.name for s in ready], results):
            if isinstance(result, Exception):
                raise result
            completed.add(name)
