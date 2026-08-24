"""
Audit Service — Logs query executions as domain events.

Publishes to the EventBus so the hot pipeline path is never blocked by I/O.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import uuid4

from reasoner.core.events.domain_events import DomainEvent, EventType

if TYPE_CHECKING:
    from reasoner.application.event_bus.bus import EventBus


class AuditService:
    def __init__(self, event_bus: EventBus):
        self._bus = event_bus

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        event = DomainEvent(
            event_id=str(uuid4()),
            event_type=EventType.QUERY_LOGGED,
            timestamp=time.time(),
            aggregate_id=user_id,
            version=1,
            metadata={
                "preset": preset,
                "method": method,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )
        await self._bus.publish(event)
