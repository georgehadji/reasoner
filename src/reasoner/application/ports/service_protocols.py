"""
Protocol classes for Reasoner service dependencies.

Enables static type-checking of ``PipelineOrchestrator`` and similar
composition boundaries without coupling to concrete implementations.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Protocol, runtime_checkable


@runtime_checkable
class PresetServiceProtocol(Protocol):
    """Minimal interface for preset resolution and router building."""

    async def resolve(self, raw_preset: str) -> tuple[str, bool, str]: ...

    def build_router(
        self,
        preset_name: str,
        custom_routing: dict[str, str] | None = None,
        agent_model: str | None = None,
    ) -> tuple[str, Any]: ...

    def build_auto_router(
        self,
        method: str,
        tier: str,
        agent_model: str | None = None,
    ) -> tuple[str, Any]: ...


@runtime_checkable
class PipelineServiceProtocol(Protocol):
    """Minimal interface for pipeline construction."""

    def create_pipeline(
        self,
        router: Any,
        preset_name: str,
        initial_state: Any | None = None,
        **kwargs: Any,
    ) -> Any: ...


@runtime_checkable
class SearchServiceProtocol(Protocol):
    """Minimal interface for web search."""

    async def search(
        self,
        query: str,
        source_type: str = "general",
        num_results: int = 10,
    ) -> list[dict[str, Any]]: ...

    async def stream_web_search_results(
        self,
        problem: str,
        run_id: str,
        num_results: int = 10,
        cancel_event: Any | None = None,
    ) -> AsyncGenerator[str, None]: ...

    async def close(self) -> None: ...


@runtime_checkable
class NeuroClientProtocol(Protocol):
    """Minimal interface for the Neuro memory HTTP client."""

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        timeout: float = 5.0,
    ) -> Any: ...

    async def close(self) -> None: ...


@runtime_checkable
class TelemetryStoreProtocol(Protocol):
    """Minimal interface for run telemetry persistence."""

    async def save_run(
        self,
        run_id: str,
        preset: str,
        method: str | None = None,
        phase_results: list[dict[str, Any]] | None = None,
        fallback_events: list[dict[str, Any]] | None = None,
        total_cost_usd: float = 0.0,
    ) -> None: ...
