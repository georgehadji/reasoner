"""Port: telemetry persistence for cross-run analytics."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from reasoner.domain.telemetry import LLMCallTelemetry, ModelRoleStats


@runtime_checkable
class CallTelemetryPort(Protocol):
    """Per-call telemetry collection for adaptive routing (ACR Phase 1).

    Records individual LLM calls and provides query methods for
    model-role performance statistics.
    """

    async def record_call(self, event: LLMCallTelemetry) -> None:
        """Persist a single LLM call telemetry event."""
        ...

    async def query_model_role_stats(
        self,
        model_id: str,
        role: str,
        window_hours: int = 168,
    ) -> ModelRoleStats:
        """Aggregate stats for a (model, role) pair over a time window."""
        ...

    async def query_role_leaderboard(
        self,
        role: str,
        window_hours: int = 168,
        limit: int = 10,
    ) -> list[ModelRoleStats]:
        """Top models for a role, ranked by composite quality score."""
        ...


__all__ = [
    "CallTelemetryPort",
]
