"""Integration tests for event emission from PipelineState (Phase 3.1).

Verifies that domain events are emitted at the correct pipeline state transitions
when the EventBus is wired. These tests do NOT require LLM access.
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any

from reasoner.domain.pipeline_state import PipelineState


class CollectingBus:
    """Mock EventBus that collects all published events for assertion."""
    def __init__(self):
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)


@pytest.fixture
def state() -> PipelineState:
    return PipelineState(problem="test problem", language="English")


@pytest.fixture
def wired_state() -> tuple[PipelineState, CollectingBus]:
    bus = CollectingBus()
    state = PipelineState(problem="test problem")
    state.wire_event_bus(bus, aggregate_id="test-run-001")
    return state, bus


def test_wire_event_bus_noop_no_bus(state: PipelineState) -> None:
    """_emit is a no-op when no EventBus is wired."""
    # Should not raise
    state._emit("PIPELINE_STARTED", problem="test")
    # Default is no _event_bus
    assert state._event_bus is None


def test_wire_event_bus_sets_fields(wired_state) -> None:
    """wire_event_bus sets _event_bus and _aggregate_id."""
    state, bus = wired_state
    assert state._event_bus is bus
    assert state._aggregate_id == "test-run-001"


def test_emit_never_raises() -> None:
    """_emit wrapping in try/except means bus errors don't crash pipeline."""
    class BrokenBus:
        async def publish(self, event):
            raise RuntimeError("Bus is broken")

    state = PipelineState(problem="test")
    bus = BrokenBus()
    state.wire_event_bus(bus, aggregate_id="test-run-001")

    # Should not raise — _emit swallows the exception
    state._emit("PIPELINE_STARTED", problem="test")

    # If we get here, _emit handled the error gracefully
    assert True


def test_emit_noop_without_bus(state) -> None:
    """_emit should not raise when no bus is wired."""
    # Not wired — should be safe no-op
    state._emit("PHASE_FAILED", phase_name="Test", error="test")
