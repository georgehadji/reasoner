"""Port: telemetry persistence for cross-run analytics."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
