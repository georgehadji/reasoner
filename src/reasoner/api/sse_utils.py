"""
SSE protocol utilities shared across streaming endpoints.

Provides:
- _event(): Format a dict as SSE data frame
- _broadcast_ws(): Fire-and-forget WebSocket broadcast
- _persist_event(): Fire-and-forget event-store persistence
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _event(data: dict) -> str:
    """Format a Python dict as a single SSE ``data:`` frame."""
    def json_serializer(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return f"data: {json.dumps(data, default=json_serializer)}\n\n"


async def _broadcast_ws(
    run_id: str, payload: dict[str, Any], _tasks: set | None = None
) -> None:
    """Broadcast a payload to WebSocket subscribers for this run.

    Fire-and-forget: never blocks the caller on WS delivery.

    If ``_tasks`` is provided, the inner broadcast task is registered there
    so callers can cancel it (e.g. on client disconnect).  Otherwise the
    task is fire-and-forget with no external cancellation handle.
    """
    try:
        from reasoner.infrastructure.websocket import get_websocket_manager
        manager = get_websocket_manager()
        task = asyncio.create_task(manager.broadcast_event(payload, run_id))
        if _tasks is not None:
            _tasks.add(task)
        task.add_done_callback(
            lambda t: (
                _tasks.discard(t) if _tasks is not None else None
            )
            or (
                logger.warning("WS broadcast failed for run %s: %s", run_id, t.exception())
                if not t.cancelled() and t.exception()
                else None
            )
        )
    except Exception:
        logger.warning("WS broadcast failed for run %s", run_id, exc_info=True)


async def _persist_event(event: Any) -> None:
    """Persist a domain event to the event store.

    Fire-and-forget: event-store failure must never break the caller.
    """
    try:
        from reasoner.infrastructure.persistence.event_store import get_event_store
        store = get_event_store()
        await store.save_events([event])
    except Exception as e:
        logger.warning(
            "EventStore persistence failed for event %s: %s",
            event.event_type.value if hasattr(event, "event_type") else "?",
            str(e),
            exc_info=True,
        )
