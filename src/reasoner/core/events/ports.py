"""Core port: EventPublisher — decouples infrastructure from application event bus."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """Minimal publish interface satisfied by EventBus and any compatible adapter."""

    async def publish(self, event: Any) -> None: ...
