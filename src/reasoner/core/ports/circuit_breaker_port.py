"""Port interface for circuit breaker — infrastructure provides concrete implementation."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class CircuitBreakerConfig:
    """Configuration for a circuit breaker instance."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 30.0


@runtime_checkable
class CircuitBreakerPort(Protocol):
    """Port for circuit breaker access.

    Implemented by infrastructure.circuit_breaker. The core layer depends
    on this port, not on the concrete circuit breaker implementation.
    """

    async def can_execute(self) -> bool: ...

    async def record_success(self) -> None: ...

    async def record_failure(self) -> None: ...

    @property
    def config(self) -> CircuitBreakerConfig: ...


class ProviderRegistryPort(Protocol):
    """Port for provider registry access.

    Implemented by infrastructure.llm.registry. Core layer depends on
    this port for building LLM providers for search/rerank tasks.
    """

    def __call__(self, model: str, **kwargs: Any) -> Any: ...
