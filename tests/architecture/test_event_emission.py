"""Integration tests for event emission via EventEmissionService (Phase 3.1 / CE 1.1).

Verifies that domain events are emitted at the correct transitions when the
EventBus is wired. EventBus wiring moved off PipelineState (removed
wire_event_bus/_emit) into EventEmissionService. These tests do NOT require LLM access.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

import pytest

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


def test_emit_outside_a_running_loop_says_so_and_does_not_leak(
    wired_emitter, caplog, recwarn
) -> None:
    """A sync caller drops the event — but leaves evidence, and no dangling coroutine.

    asyncio.create_task raises RuntimeError with no running loop, so every
    event of a synchronous run was discarded by `except Exception: pass`. The
    already-built bus.publish coroutine was then never awaited, surfacing at
    GC time as a RuntimeWarning blamed on the swallow line rather than on the
    caller. P5, docs/plans/root-cause-remediation-2026-09-07.md.
    """
    emitter, bus = wired_emitter

    with caplog.at_level(logging.WARNING, logger="reasoner.core.degrade"):
        emitter.emit("PIPELINE_STARTED", problem="test")

    assert bus.events == [], "no running loop, so nothing can have been published"
    assert any(
        "site=events.emit.no_running_loop" in r.getMessage() for r in caplog.records
    ), f"expected a degradation record, got: {[r.getMessage() for r in caplog.records]}"

    gc.collect()
    assert not [w for w in recwarn.list if w.category is RuntimeWarning], (
        "the un-awaited bus.publish coroutine leaked"
    )


@pytest.mark.asyncio
async def test_emit_inside_a_running_loop_still_publishes(wired_emitter) -> None:
    """The guard above must not have cost us the normal path."""
    emitter, bus = wired_emitter
    emitter.emit("PIPELINE_STARTED", problem="test")
    await asyncio.sleep(0)  # let the fire-and-forget task run
    assert len(bus.events) == 1
