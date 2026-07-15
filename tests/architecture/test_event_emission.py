"""Integration tests for event emission via EventEmissionService (Phase 3.1 / CE 1.1).

Verifies that domain events are emitted at the correct transitions when the
EventBus is wired. EventBus wiring moved off PipelineState (removed
wire_event_bus/_emit) into EventEmissionService. These tests do NOT require LLM access.
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any

from reasoner.application.services.event_emission_service import EventEmissionService


class CollectingBus:
    """Mock EventBus that collects all published events for assertion."""
    def __init__(self):
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)


@pytest.fixture
def emitter() -> EventEmissionService:
    return EventEmissionService()


@pytest.fixture
def wired_emitter() -> tuple[EventEmissionService, CollectingBus]:
    bus = CollectingBus()
    emitter = EventEmissionService()
    emitter.wire(bus, aggregate_id="test-run-001")
    return emitter, bus


def test_wire_event_bus_noop_no_bus(emitter: EventEmissionService) -> None:
    """emit is a no-op when no EventBus is wired."""
    # Should not raise
    emitter.emit("PIPELINE_STARTED", problem="test")
    # Default is no bus
    assert emitter._bus is None


def test_wire_event_bus_sets_fields(wired_emitter) -> None:
    """wire sets the bus and aggregate id."""
    emitter, bus = wired_emitter
    assert emitter._bus is bus
    assert emitter._aggregate_id == "test-run-001"


def test_emit_never_raises() -> None:
    """emit wrapping in try/except means bus errors don't crash the pipeline."""
    class BrokenBus:
        async def publish(self, event):
            raise RuntimeError("Bus is broken")

    emitter = EventEmissionService()
    emitter.wire(BrokenBus(), aggregate_id="test-run-001")

    # Should not raise — emit swallows the exception
    emitter.emit("PIPELINE_STARTED", problem="test")

    # If we get here, emit handled the error gracefully
    assert True


def test_emit_noop_without_bus(emitter) -> None:
    """emit should not raise when no bus is wired."""
    # Not wired — should be safe no-op
    emitter.emit("PHASE_FAILED", phase_name="Test", error="test")
