"""
Application Layer - Event Bus

The event bus distributes domain events to subscribers.
This enables:
- Decoupled communication between components
- Async processing
- Multiple side effects from single events
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable
from collections import defaultdict
import time # New import

from reasoner.core.settings import settings
from reasoner.core.events.domain_events import DomainEvent, EventType, _AllEventType, PipelineEventType
from reasoner.infrastructure.observability.langfuse_subscriber import get_langfuse_subscriber # New import

logger = logging.getLogger(__name__)

# Dead-letter log for events that exhaust all retries
_DEAD_LETTER_PATH = Path(__file__).parent.parent.parent / "logs" / "dead_letter_events.jsonl"
_DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)


# Type alias for event handlers
EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """
    In-memory event bus for domain events.
    
    Supports:
    - Synchronous and async handlers
    - Event type filtering
    - Wildcard subscriptions
    - Error isolation (one handler failure doesn't affect others)
    """
    
    def __init__(self, max_queue_size: int = 1000):
        self._handlers: dict[_AllEventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._error_handlers: list[Callable[[DomainEvent, Exception], Awaitable[None]]] = []
        self._running = False
        self._max_queue_size: int = max_queue_size
        self._task_queue: asyncio.Queue[tuple[DomainEvent, EventHandler]] | None = None
        self._semaphore = asyncio.Semaphore(200)  # Max 200 concurrent handler executions
    
    def subscribe(
        self,
        event_type: _AllEventType,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe to a specific event type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Async function to call when event occurs
        """
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed handler to {event_type.value}")
    
    def subscribe_all(
        self,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe to all events.
        
        Args:
            handler: Async function to call for every event
        """
        self._global_handlers.append(handler)
        logger.debug("Subscribed global handler")
    
    def on_error(
        self,
        handler: Callable[[DomainEvent, Exception], Awaitable[None]],
    ) -> None:
        """
        Register error handler for handler failures.
        
        Args:
            handler: Async function called when a handler fails
        """
        self._error_handlers.append(handler)
    
    async def start(self) -> None:
        """Start the background queue consumer."""
        if self._running:
            return
        self._task_queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._running = True
        self._worker_task = asyncio.create_task(self._queue_worker())

    async def stop(self) -> None:
        """Stop the background queue consumer."""
        if not self._running:
            return
        self._running = False
        if hasattr(self, "_worker_task"):
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _queue_worker(self) -> None:
        """Background worker that consumes the event queue."""
        while self._running:
            try:
                event, handler = await self._task_queue.get()
                await self._safe_execute(handler, event)
                self._task_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Queue worker error: %s", exc)

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish an event to all subscribers.

        Handlers are called concurrently with bounded concurrency.
        Errors in one handler don't affect others.

        Args:
            event: Domain event to publish
        """
        # Snapshot handler lists to avoid racing with concurrent subscribe() calls
        handlers = list(self._handlers.get(event.event_type, [])) + list(self._global_handlers)

        if not handlers:
            logger.debug("No handlers for %s", event.event_type.value)
            return

        # If queue mode is active, enqueue events with backpressure
        if self._running and self._task_queue is not None:
            for handler in handlers:
                try:
                    if event.is_critical:
                        await self._task_queue.put((event, handler)) # Apply backpressure for critical events
                    else:
                        self._task_queue.put_nowait((event, handler)) # Drop non-critical if queue is full
                except asyncio.QueueFull:
                    logger.error(
                        "Event bus queue full; %s event %s dropped.",
                        "Critical" if event.is_critical else "Non-critical",
                        event.event_id,
                    )
                    # For critical events that are dropped due to full queue, also log to dead-letter
                    if event.is_critical:
                        asyncio.create_task(self._log_to_dead_letter(event, "Queue full"))
            return

        # Execute all handlers concurrently with bounded concurrency
        async def _bounded(handler: EventHandler) -> None:
            async with self._semaphore:
                await self._safe_execute(handler, event)

        tasks = [asyncio.create_task(_bounded(h)) for h in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_execute(
        self,
        handler: EventHandler,
        event: DomainEvent,
    ) -> None:
        """Execute handler with error isolation and retry."""
        max_retries = 3
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                await handler(event)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = min(2 ** attempt, 8)  # cap at 8s
                    logger.warning(
                        "Handler error for %s (attempt %d/%d), retrying in %.1fs: %s",
                        event.event_type.value, attempt + 1, max_retries + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Handler error for %s exhausted all retries: %s",
                        event.event_type.value, exc,
                        exc_info=True,
                    )

        # Notify error handlers
        # Notify error handlers
        for error_handler in self._error_handlers:
            try:
                await error_handler(event, last_exc)
            except Exception as inner_exc:
                logger.error("Error handler failed: %s", inner_exc)

        # Dead-letter log
        await self._log_to_dead_letter(event, str(last_exc))

    async def _log_to_dead_letter(self, event: DomainEvent, error_message: str, handler_name: str = "") -> None:
        """Log event to dead-letter file."""
        try:
            entry = {
                "event_type": event.event_type.value,
                "aggregate_id": event.aggregate_id,
                "event_id": event.event_id,
                "error": error_message,
                "handler": handler_name,
                "timestamp": time.time(),
                "is_critical": event.is_critical,
            }
            # Use asyncio.to_thread for blocking file I/O
            await asyncio.to_thread(lambda: _DEAD_LETTER_PATH.open("a", encoding="utf-8").write(json.dumps(entry, default=str) + "\n"))
        except Exception as dl_exc:
            logger.error("Failed to write dead-letter entry: %s", dl_exc)

    def clear(self) -> None:
        """Clear all subscriptions."""
        self._handlers.clear()
        self._global_handlers.clear()
        self._error_handlers.clear()
    
    def get_subscriber_count(self, event_type: _AllEventType) -> int:
        """Get number of subscribers for an event type."""
        return len(self._handlers.get(event_type, []))
    
    @property
    def total_subscribers(self) -> int:
        """Get total number of subscribers."""
        return (
            sum(len(handlers) for handlers in self._handlers.values()) +
            len(self._global_handlers)
        )


# ─────────────────────────────────────────────────────────────────────
# GLOBAL EVENT BUS INSTANCE
# ─────────────────────────────────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _event_bus
    _event_bus = None


# ─────────────────────────────────────────────────────────────────────
# EVENT HANDLER DECORATORS
# ─────────────────────────────────────────────────────────────────────

def handle_event(event_type: _AllEventType) -> Callable[[EventHandler], EventHandler]:
    """
    Decorator to register an event handler.
    
    Usage:
        @handle_event(EventType.PHASE_COMPLETED)
        async def on_phase_completed(event: DomainEvent):
            ...
    """
    def decorator(handler: EventHandler) -> EventHandler:
        bus = get_event_bus()
        bus.subscribe(event_type, handler)
        return handler
    
    return decorator


def handle_all_events() -> Callable[[EventHandler], EventHandler]:
    """
    Decorator to subscribe to all events.
    
    Usage:
        @handle_all_events()
        async def on_any_event(event: DomainEvent):
            ...
    """
    def decorator(handler: EventHandler) -> EventHandler:
        bus = get_event_bus()
        bus.subscribe_all(handler)
        return handler
    
    return decorator


# ─────────────────────────────────────────────────────────────────────
# EXAMPLE SUBSCRIBERS
# ─────────────────────────────────────────────────────────────────────

async def log_all_events(event: DomainEvent) -> None:
    """Log all events for debugging."""
    logger.debug(
        f"Event: {event.event_type.value} "
        f"(aggregate: {event.aggregate_id}, version: {event.version})"
    )


async def track_pipeline_metrics(event: DomainEvent) -> None:
    """Track metrics for pipeline events."""
    from reasoner.core.events.domain_events import (
        PipelineCompleted,
        PipelineFailed,
        PhaseCompleted,
    )
    
    if isinstance(event, PipelineCompleted):
        logger.info(
            f"Pipeline completed: {event.total_duration_seconds:.2f}s, "
            f"{event.total_tokens.get('total', 0)} tokens"
        )
    elif isinstance(event, PipelineFailed):
        logger.warning(f"Pipeline failed: {event.error}")
    elif isinstance(event, PhaseCompleted):
        logger.debug(
            f"Phase {event.phase_name} completed: "
            f"{event.duration_seconds:.2f}s"
        )


async def persist_all_events(event: DomainEvent) -> None:
    """Persist all events to the EventStore for audit trail and replay.

    The EventBus already runs handlers in a dedicated worker task with
    queue-based backpressure, so we call EventStore.save_events directly.
    """
    try:
        from reasoner.infrastructure.persistence.event_store import get_event_store
        store = get_event_store()
        await store.save_events([event])
    except Exception as exc:
        logger.warning("EventStore persistence failed for %s: %s", event.event_type.value, exc)


async def init_default_subscribers(bus: EventBus | None = None) -> None:
    """
    Register default subscribers.

    Call this once on application startup, not at module import.
    Tests should call reset_event_bus() in teardown to clean up.
    """
    if bus is None:
        bus = get_event_bus()
    bus.subscribe_all(log_all_events)
    bus.subscribe_all(track_pipeline_metrics)
    bus.subscribe_all(persist_all_events)

    # Initialize and register Langfuse subscriber if enabled
    # Check if Langfuse keys are set in environment variables
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        langfuse_subscriber = await get_langfuse_subscriber()
        # The _is_langfuse_enabled check is now inside the get_langfuse_subscriber factory
        # We only proceed if an active subscriber is returned.
        if langfuse_subscriber._is_langfuse_enabled:
            bus.subscribe(PipelineEventType.LLM_GENERATION_COMPLETED, langfuse_subscriber.handle_llm_generation_completed)
            bus.subscribe(PipelineEventType.PIPELINE_STARTED, langfuse_subscriber.handle_pipeline_started)
            bus.subscribe(PipelineEventType.PIPELINE_COMPLETED, langfuse_subscriber.handle_pipeline_completed)
            bus.subscribe(PipelineEventType.PIPELINE_FAILED, langfuse_subscriber.handle_pipeline_failed)
            logger.info("Langfuse subscriber registered with EventBus.")