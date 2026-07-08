"""Port: telemetry persistence for cross-run analytics."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from reasoner.domain.telemetry import LLMCallTelemetry, ModelRoleStats


@runtime_checkable
class TelemetryStorePort(Protocol):
    """Queryable per-phase telemetry for cross-run analytics."""

    async def save_run(
        self,
        run_id: str,
        preset: str,
        method: str | None,
        phase_results: list[dict[str, Any]],
        fallback_events: list[dict[str, Any]],
        total_cost_usd: float,
    ) -> None: ...

    async def query_by_preset(
        self, preset: str, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def query_recent(
        self, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def get_preset_stats(
        self, preset: str
    ) -> dict[str, Any]: ...


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
    "TelemetryStorePort",
    "CallTelemetryPort",
]
