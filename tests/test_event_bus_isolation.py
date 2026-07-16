"""
Tests for Event Bus subscriber isolation.

Verifies that init_default_subscribers() is not called at import time
and that reset_event_bus() properly clears state.
"""

import pytest

from reasoner.application.event_bus.bus import (
    get_event_bus,
    reset_event_bus,
    init_default_subscribers,
)


class TestEventBusIsolation:
    """Tests for import-time side-effect prevention."""

    @pytest.fixture(autouse=True)
    def clean_bus(self):
        """Reset the global bus before and after every test."""
        reset_event_bus()
        yield
        reset_event_bus()

    def test_subscribers_not_registered_at_import(self):
        """
        After a fresh reset, the bus should have zero subscribers.
        This verifies that init_default_subscribers() is NOT called at module import.
        """
        bus = get_event_bus()
        assert bus.total_subscribers == 0

    @pytest.mark.asyncio
    async def test_init_default_subscribers_registers_handlers(self):
        bus = get_event_bus()
        assert bus.total_subscribers == 0

        await init_default_subscribers(bus)
        assert bus.total_subscribers > 0

    @pytest.mark.asyncio
    async def test_duplicate_init_is_detectable(self):
        """
        init_default_subscribers() appends handlers without deduplication.
        This documents the current behavior; future work could add idempotency.
        """
        bus = get_event_bus()
        await init_default_subscribers(bus)
        first_count = bus.total_subscribers

        await init_default_subscribers(bus)
        second_count = bus.total_subscribers

        assert second_count > first_count

    @pytest.mark.asyncio
    async def test_reset_event_bus_clears_handlers(self):
        bus = get_event_bus()
        await init_default_subscribers(bus)
        assert bus.total_subscribers > 0

        reset_event_bus()
        new_bus = get_event_bus()
        assert new_bus.total_subscribers == 0

    @pytest.mark.asyncio
    async def test_event_published_after_init(self):
        from reasoner.core.events.domain_events import EventType, make_event

        bus = get_event_bus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.PIPELINE_STARTED, handler)
        await init_default_subscribers(bus)

        event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="test-pipeline",
            version=1,
            problem="Test",
            preset="test",
            method="test",
        )
        await bus.publish(event)

        # Our handler + any default global handlers should have fired
        assert len(received) >= 1
        assert received[0].event_type == EventType.PIPELINE_STARTED
