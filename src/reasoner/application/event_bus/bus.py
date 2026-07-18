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
import os
import random
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
_DEAD_LETTER_MAX_BYTES = 100 * 1024 * 1024  # 100 MB cap before rotation
# Note: _DEAD_LETTER_PATH.parent.mkdir() moved to EventBus.start() to avoid
# PermissionError on read-only filesystems at import time.


async def _rotate_dead_letter_if_needed() -> None:
    """Rotate the dead-letter JSONL if it exceeds the size cap."""
    try:
        if _DEAD_LETTER_PATH.exists() and _DEAD_LETTER_PATH.stat().st_size > _DEAD_LETTER_MAX_BYTES:
            import time as _time
            archive_name = f"dead_letter_events_{_time.strftime('%Y%m%d_%H%M%S')}.jsonl"
            archive_path = _DEAD_LETTER_PATH.with_name(archive_name)
            _DEAD_LETTER_PATH.rename(archive_path)
            logger.info(
                "Rotated dead-letter log: %s -> %s (size exceeded %dMB)",
                _DEAD_LETTER_PATH.name, archive_name, _DEAD_LETTER_MAX_BYTES // (1024 * 1024),
            )
    except Exception as exc:
        logger.warning("Dead-letter rotation failed: %s", exc)


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
        self._dropped_event_count: int = 0
        self._dead_letter_enabled: bool = True
    
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
        try:
            _DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._dead_letter_enabled = True
        except PermissionError:
            logger.warning(
                "Cannot create dead-letter log directory %s — dead-letter logging disabled.",
                _DEAD_LETTER_PATH.parent,
            )
            self._dead_letter_enabled = False
        self._task_queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._running = True
        self._worker_task = asyncio.create_task(self._queue_worker())
        self._worker_task.add_done_callback(self._on_worker_exit)

    def _on_worker_exit(self, task: asyncio.Task) -> None:
        """Handle unexpected worker exit."""
        self._running = False
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("Event bus worker task cancelled.")
        except Exception as exc:
            logger.critical("Event bus worker task crashed: %s", exc, exc_info=True)

    async def stop(self) -> None:
        """Stop the background queue consumer."""
        if not self._running:
            return
        self._running = False
        await self.drain(timeout=5.0)
        if hasattr(self, "_worker_task"):
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def drain(self, timeout: float = 5.0) -> None:
        """Process all queued events before shutdown.

        Waits up to ``timeout`` seconds for the queue to empty.
        Events not processed within the timeout are logged to dead-letter.
        """
        if self._task_queue is None or self._task_queue.empty():
            return
        try:
            await asyncio.wait_for(self._task_queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            remaining = self._task_queue.qsize()
            logger.warning(
                "EventBus drain timed out after %.1fs with %d events remaining.",
                timeout,
                remaining,
            )
            self._dropped_event_count += remaining

    async def _queue_worker(self) -> None:
        """Background worker that consumes the event queue."""
        while self._running:
            try:
                event, handler = await self._task_queue.get()
                try:
                    await self._safe_execute(handler, event)
                finally:
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
                    self._dropped_event_count += 1
                    logger.warning(
                        "Event bus queue full; %s event %s dropped (total_dropped=%d).",
                        "Critical" if event.is_critical else "Non-critical",
                        event.event_id,
                        self._dropped_event_count,
                    )
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
                    wait = min(2 ** attempt, 8) + random.uniform(0, 1.0)  # cap at 8s + jitter
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
        if not getattr(self, '_dead_letter_enabled', True):
            return
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
            # Increment dead-letter counter
            try:
                from reasoner.metrics import DEAD_LETTER_EVENTS
                DEAD_LETTER_EVENTS.labels(event_type=event.event_type.value).inc()
            except Exception:
                pass
            # Rotate if needed (async check before blocking write)
            await _rotate_dead_letter_if_needed()
            # Use asyncio.to_thread for blocking file I/O
            def _write_dead_letter():
                with _DEAD_LETTER_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            await asyncio.to_thread(_write_dead_letter)
        except Exception as dl_exc:
            logger.error("Failed to write dead-letter entry: %s", dl_exc)

    def stats(self) -> dict[str, int | bool]:
        """Return observable metrics for the event bus."""
        return {
            "dropped_event_count": self._dropped_event_count,
            "queue_size": self._task_queue.qsize() if self._task_queue else 0,
            "total_subscribers": self.total_subscribers,
            "running": self._running,
        }

    def clear(self) -> None:
        """Clear all subscriptions."""
        self._handlers.clear()
        self._global_handlers.clear()
        self._error_handlers.clear()
    
    @property
    def dropped_event_count(self) -> int:
        """Total events dropped since startup due to full queue."""
        return self._dropped_event_count

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
        token_info = event.total_tokens
        if isinstance(token_info, dict):
            token_str = f"{token_info.get('total', 0)} tokens"
        else:
            token_str = f"{token_info} tokens"
        logger.info(
            f"Pipeline completed: {event.total_duration_seconds:.2f}s, "
            f"{token_str}"
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

    # ── Transactional Email Notifications (P2.14) ──
    _register_notification_subscriber(bus)


def _register_notification_subscriber(bus: "EventBus") -> None:
    """Register the email notification subscriber for critical events."""
    from reasoner.core.settings import settings as _s
    if not _s.NOTIFICATION_EMAIL:
        logger.info("NOTIFICATION_EMAIL not configured — skipping email notification subscriber")
        return

    adapter = None
    if _s.RESEND_API_KEY:
        try:
            from reasoner.infrastructure.email.resend_adapter import ResendEmailAdapter
            adapter = ResendEmailAdapter()
        except Exception as exc:
            logger.warning("Failed to initialize Resend adapter: %s", exc)

    try:
        from reasoner.application.services.notification_subscriber import NotificationSubscriber
        subscriber = NotificationSubscriber(email_adapter=adapter)
        from reasoner.core.events.domain_events import SaaSEventType, PipelineEventType
        # Subscribe to critical SaaS events
        bus.subscribe(SaaSEventType.WEBHOOK_PROCESSING_FAILED, subscriber.handle_critical_event)
        bus.subscribe(SaaSEventType.SPEND_CAP_EXCEEDED, subscriber.handle_critical_event)
        bus.subscribe(SaaSEventType.PAYMENT_FAILED, subscriber.handle_critical_event)
        bus.subscribe(SaaSEventType.PAYMENT_SUCCEEDED, subscriber.handle_critical_event)
        bus.subscribe(SaaSEventType.SUBSCRIPTION_CANCELLED, subscriber.handle_critical_event)
        bus.subscribe(PipelineEventType.PIPELINE_FAILED, subscriber.handle_critical_event)
        logger.info(
            "Notification subscriber registered%s.",
            "" if adapter else " (no email adapter — events will be logged only)",
        )
    except Exception as exc:
        logger.warning("Failed to register notification subscriber: %s", exc)