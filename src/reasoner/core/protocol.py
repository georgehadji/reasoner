"""
Core abstractions for the Reasoner pipeline.

PhaseConfig  — per-phase LLM parameters (max_tokens, temperature, timeout, role)
PhaseResult  — immutable output of one phase execution
Phase        — typing.Protocol that all phase classes satisfy
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from reasoner.domain.pipeline_state import PipelineState
    from reasoner.infrastructure.llm.router import ProviderRouter


from reasoner.core.constants import DEFAULT_MAX_TOKENS


class TemperatureStrategy(Enum):
    """How temperature should adapt on retry."""
    FIXED = "fixed"           # Always use configured temperature
    ESCALATE = "escalate"     # Increase by 0.1 per retry (creative phases)
    DEESCALATE = "deescalate" # Decrease by 0.05 per retry (structured phases)
    SWEEP = "sweep"           # Try 0.1, 0.5, 0.9 across retries


@dataclass(frozen=True)
class PhaseConfig:
    """
    LLM call parameters for a single phase.
    Frozen so preset overrides produce new instances rather than mutations.
    """
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = 1.0
    timeout_seconds: float | None = None  # None = no timeout
    role: str = "primary"                 # ProviderRouter lookup key
    temperature_strategy: TemperatureStrategy = TemperatureStrategy.FIXED

    def with_overrides(self, **kwargs: Any) -> "PhaseConfig":
        """Return a new PhaseConfig with selected fields replaced."""
        return replace(self, **kwargs)


@dataclass(frozen=True)
class PhaseResult:
    """
    Immutable record of one phase's execution.
    Accumulated in PipelineState.phase_results for observability and future resume support.
    """
    phase_name: str
    output: Any                             # Concrete type varies per phase; Any here for the protocol
    tokens: dict[str, int]                  # {"input": N, "output": N}
    model_used: str
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
    raw_response: str = ""

    @property
    def succeeded(self) -> bool:
        return self.output is not None and not self.errors


def make_phase_result(
    phase_name: str,
    output: Any,
    tokens: dict[str, int],
    model_used: str,
    start_time: float,
    errors: list[str] | None = None,
    raw_response: str = "",
) -> PhaseResult:
    """Convenience constructor that computes duration from a start timestamp."""
    return PhaseResult(
        phase_name=phase_name,
        output=output,
        tokens=tokens,
        model_used=model_used,
        duration_seconds=time.monotonic() - start_time,
        errors=errors or [],
        raw_response=raw_response,
    )


@runtime_checkable
class Phase(Protocol):
    """
    Protocol for pipeline phases. Does NOT require inheritance —
    any class with (name: str, config: PhaseConfig, async execute(...)) satisfies it.
    """
    name: str
    config: PhaseConfig

    async def execute(
        self,
        state: "PipelineState",
        router: "ProviderRouter",
    ) -> PhaseResult:
        ...
