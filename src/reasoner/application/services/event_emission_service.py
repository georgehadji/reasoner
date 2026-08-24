"""Event Emission Service — manages domain event publishing for pipeline execution.

Decouples event emission from PipelineState (which should be pure data).
The orchestrator creates one EventEmissionService per pipeline run and
injects it into the execution context. Phase functions access it via
the module-level getter, which resolves from a contextvar for correct
per-run isolation.

Critical Enhancements:
- CE 1.1: EventBus wiring moved off PipelineState (removed wire_event_bus, _emit).
- CE 1.2: Bounded pending-event buffer with backpressure.
- CE 1.3: contextvar-based injection for deep callers (phase functions).
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any

from reasoner.core.events.domain_events import make_event

logger = logging.getLogger(__name__)

# ── Contextvar for per-run emitter injection ─────────────────────────
# Phase functions that call emit() (e.g. cognitive_phases.py) retrieve
# the current emitter via get_event_emitter() — no PipelineState coupling.
_current_emitter: ContextVar[EventEmissionService | None] = ContextVar(
    "_current_emitter", default=None
)


def get_event_emitter() -> EventEmissionService | None:
    """Get the active EventEmissionService for the current pipeline run.

    Returns None outside of an active pipeline execution context
    (e.g. during tests or CLI-only runs).
    """
    return _current_emitter.get()


def set_event_emitter(emitter: EventEmissionService | None) -> None:
    """Set the active EventEmissionService for the current pipeline run."""
    _current_emitter.set(emitter)


class EventEmissionService:
    """Manages domain event publishing during a single pipeline run.

    Owns the EventBus wiring and provides emit/append_pending operations
    that were previously on PipelineState. The service is created in the
    execution layer (api/execution/pipeline.py) and scoped to one run.

    Usage::

        emitter = EventEmissionService(event_bus, aggregate_id="run-123")
        with emitter.context():
            state = PipelineState(...)
            emitter.emit("PIPELINE_STARTED", problem="...")
            emitter.append_pending_event({"type": "phase_update", ...})
    """

    MAX_PENDING_EVENTS: int = 1000

    def __init__(
        self,
        bus: Any | None = None,
        aggregate_id: str = "",
    ) -> None:
        self._bus = bus
        self._aggregate_id = aggregate_id
        # Pending events buffer — flushed by the SSE streaming layer
        self.pending_events: list[dict[str, Any]] = []

    def context(self) -> _EmitterContext:
        """Return a context manager that sets this emitter as the current one.

        Phase functions that call get_event_emitter() will resolve to
        this instance while the context is active.
        """
        return _EmitterContext(self)

    # ── Event Bus Wiring ────────────────────────────────────────────

    def wire(self, bus: Any, aggregate_id: str = "") -> None:
        """Wire an EventBus for domain event publishing during pipeline execution.

        Can be called after construction to lazily set the bus.
        """
        self._bus = bus
        if aggregate_id:
            self._aggregate_id = aggregate_id

    # ── Domain Event Emission ────────────────────────────────────────

    def emit(self, event_type: str, **event_kwargs: Any) -> None:
        """Emit a domain event through the wired EventBus (fire-and-forget).

        Accepts string event_type (e.g. "PIPELINE_STARTED") or enum member.
        No-op if no EventBus is wired. Events are published asynchronously
        — this method does not await the publish and never raises.
        """
        bus = self._bus
        if bus is None:
            return
        try:
            # Coerce string to proper PipelineEventType enum member.
            # Note: PipelineEventType inherits from (str, Enum), so
            # lookup must be by VALUE (lowercase), not by NAME (uppercase).
            # BUGFIX v3.2: Use .lower() instead of .upper() — the old code
            # (upper) silently swallowed all events because `str, Enum`
            # resolves by value, not name. The event type values are
            # lowercase strings like "pipeline_started".
            if isinstance(event_type, str):
                from reasoner.core.events.domain_events import PipelineEventType as _PET_
                event_type = _PET_(event_type.lower())

            event = make_event(
                event_type,
                aggregate_id=self._aggregate_id,
                version=1,
                **event_kwargs,
            )
            # Fire-and-forget: create a task for the bus.publish
            task = asyncio.create_task(bus.publish(event))
            task.add_done_callback(
                lambda t: logger.error(
                    "Event publish failed: %s", t.exception()
                )
                if not t.cancelled() and t.exception()
                else None
            )
        except Exception:
            pass  # Never let event publishing crash the pipeline

    # ── Pending Events Buffer ───────────────────────────────────────

    def append_pending_event(self, event: dict[str, Any]) -> None:
        """Append event with bounded backpressure."""
        if len(self.pending_events) >= self.MAX_PENDING_EVENTS:
            # Drop oldest 10% to make room
            drop_count = self.MAX_PENDING_EVENTS // 10
            self.pending_events = self.pending_events[drop_count:]
        self.pending_events.append(event)

    def pop_pending_events(self) -> list[dict[str, Any]]:
        """Remove and return all pending events (used by SSE streaming)."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


class _EmitterContext:
    """Context manager that scopes an EventEmissionService to a pipeline run."""

    def __init__(self, emitter: EventEmissionService) -> None:
        self._emitter = emitter
        self._token: Any = None

    def __enter__(self) -> EventEmissionService:
        self._token = _current_emitter.set(self._emitter)
        return self._emitter

    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            _current_emitter.reset(self._token)
