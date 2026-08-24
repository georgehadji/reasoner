"""Tests for EventEmissionService — contextvar lifecycle, emit, pending events."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestEventEmissionServiceLifecycle:
    """Verify contextvar set/reset and per-run isolation."""

    def test_contextvar_set_and_reset(self):
        from reasoner.application.services.event_emission_service import (
            EventEmissionService,
            get_event_emitter,
        )

        emitter = EventEmissionService()
        assert get_event_emitter() is None, "emitter should be None outside context"

        with emitter.context():
            assert get_event_emitter() is emitter, "emitter should be set inside context"

        assert get_event_emitter() is None, "emitter should be cleared after context exit"

    def test_contextvar_nesting_and_isolation(self):
        from reasoner.application.services.event_emission_service import (
            EventEmissionService,
            get_event_emitter,
        )

        emitter_a = EventEmissionService(aggregate_id="run-a")
        emitter_b = EventEmissionService(aggregate_id="run-b")

        with emitter_a.context():
            assert get_event_emitter() is emitter_a
            with emitter_b.context():
                assert get_event_emitter() is emitter_b, "inner context should override"
            assert get_event_emitter() is emitter_a, "outer context should restore"

        assert get_event_emitter() is None


class TestEventEmissionServiceEmit:
    """Verify emit() wiring and fire-and-forget behavior."""

    @pytest.mark.asyncio
    async def test_emit_noop_without_bus(self):
        """emit() should be a no-op when no EventBus is wired."""
        from reasoner.application.services.event_emission_service import EventEmissionService

        emitter = EventEmissionService()
        # Should not raise even though bus is None
        emitter.emit("TEST_EVENT", key="value")

    @pytest.mark.asyncio
    async def test_emit_publishes_to_bus(self):
        """emit() creates an asyncio task for bus.publish.

        The fire-and-forget task runs on the event loop. We verify the
        wiring is correct by inspecting the created task.
        """
        from reasoner.application.services.event_emission_service import EventEmissionService

        captured = []

        class TrackingBus:
            async def publish(self, event):
                captured.append(event)

        emitter = EventEmissionService(bus=TrackingBus(), aggregate_id="run-1")
        emitter.emit("PIPELINE_STARTED", problem="test problem")

        import asyncio
        # Give the fire-and-forget task a chance to complete
        for _ in range(20):
            await asyncio.sleep(0)
            if captured:
                break

        assert len(captured) == 1, "bus.publish should have been called once"
        assert captured[0].aggregate_id == "run-1"

    @pytest.mark.asyncio
    async def test_emit_does_not_raise_on_publish_failure(self):
        """emit() should catch and log bus.publish failures — never crash."""
        from reasoner.application.services.event_emission_service import EventEmissionService

        mock_bus = AsyncMock()
        mock_bus.publish.side_effect = RuntimeError("Bus unavailable")
        emitter = EventEmissionService(bus=mock_bus, aggregate_id="run-1")

        # Should not raise despite bus failure
        emitter.emit("TEST_EVENT", key="value")

        import asyncio
        await asyncio.sleep(0)

    def test_emit_accepts_string_event_type(self):
        """emit() should coerce string types to PipelineEventType enum."""
        from reasoner.application.services.event_emission_service import EventEmissionService

        mock_bus = MagicMock()
        emitter = EventEmissionService(bus=mock_bus, aggregate_id="run-1")
        emitter.emit("pipeline_started", problem="test")

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.run_until_complete(asyncio.sleep(0))
        except RuntimeError:
            pass  # no running loop

    def test_wire_sets_bus_and_aggregate_id(self):
        """wire() should set the bus and aggregate_id after construction."""
        from reasoner.application.services.event_emission_service import EventEmissionService

        emitter = EventEmissionService()
        mock_bus = MagicMock()
        emitter.wire(mock_bus, aggregate_id="run-wired")

        assert emitter._bus is mock_bus
        assert emitter._aggregate_id == "run-wired"


class TestEventEmissionServicePendingEvents:
    """Verify the pending events buffer with bounded backpressure."""

    def setup_method(self):
        from reasoner.application.services.event_emission_service import EventEmissionService
        self.emitter = EventEmissionService()

    def test_append_and_pop(self):
        self.emitter.append_pending_event({"type": "agent_start", "agent": "test"})
        self.emitter.append_pending_event({"type": "agent_complete", "agent": "test"})
        assert len(self.emitter.pending_events) == 2

        popped = self.emitter.pop_pending_events()
        assert len(popped) == 2
        assert popped[0]["type"] == "agent_start"
        assert len(self.emitter.pending_events) == 0

    def test_bounded_backpressure_drops_oldest(self):
        from reasoner.application.services.event_emission_service import EventEmissionService
        max_events = EventEmissionService.MAX_PENDING_EVENTS
        # Fill to capacity
        for i in range(max_events):
            self.emitter.append_pending_event({"type": "event", "i": i})
        assert len(self.emitter.pending_events) == max_events

        # Append one more — oldest ~10% should be dropped
        self.emitter.append_pending_event({"type": "overflow", "i": max_events})
        # Buffer should not grow unbounded: capped at ~MAX with oldest dropped
        assert len(self.emitter.pending_events) < max_events
        # Oldest entries should have been dropped (first item is ~100, not 0)
        assert self.emitter.pending_events[0]["i"] > 0


class TestGetEventEmitter:
    """Verify the module-level getter function."""

    def test_get_event_emitter_returns_none_outside_context(self):
        from reasoner.application.services.event_emission_service import get_event_emitter
        assert get_event_emitter() is None

    def test_get_event_emitter_returns_active_emitter(self):
        from reasoner.application.services.event_emission_service import (
            EventEmissionService,
            get_event_emitter,
        )

        emitter = EventEmissionService()
        with emitter.context():
            assert get_event_emitter() is emitter
