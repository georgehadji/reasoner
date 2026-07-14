"""
Tests for Event Bus

Tests the publish-subscribe event distribution system.
"""

import pytest
import asyncio

from reasoner.application.event_bus.bus import (
    EventBus,
    get_event_bus,
    reset_event_bus,
    handle_event,
    handle_all_events,
)
from reasoner.core.events.domain_events import (
    EventType,
    make_event,
    PipelineStarted,
    PhaseCompleted,
)


@pytest.fixture
def event_bus():
    """Create fresh event bus for each test."""
    reset_event_bus()
    bus = get_event_bus()
    yield bus
    reset_event_bus()


class TestEventBus:
    """Tests for EventBus class."""
    
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus):
        """Test basic subscribe and publish."""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, handler)
        
        event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="test-123",
            version=1,
            phase_name="classification",
            result={},
            tokens={},
            model_used="test",
            duration_seconds=1.0,
        )
        
        await event_bus.publish(event)
        
        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.PHASE_COMPLETED
    
    @pytest.mark.asyncio
    async def test_subscribe_all(self, event_bus):
        """Test subscribing to all events."""
        received_events = []
        
        async def handler(event):
            received_events.append(event)
        
        event_bus.subscribe_all(handler)
        
        # Publish different event types
        for event_type in [EventType.PHASE_STARTED, EventType.PHASE_COMPLETED]:
            event = make_event(
                event_type,
                aggregate_id="test-123",
                version=1,
            )
            await event_bus.publish(event)
        
        assert len(received_events) == 2
    
    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, event_bus):
        """Test that one handler error doesn't affect others."""
        received = []
        
        async def good_handler(event):
            received.append("good")
        
        async def bad_handler(event):
            raise ValueError("Handler error")
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, good_handler)
        event_bus.subscribe(EventType.PHASE_COMPLETED, bad_handler)
        event_bus.subscribe(EventType.PHASE_COMPLETED, good_handler)
        
        event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="test-123",
            version=1,
        )
        
        # Should not raise despite bad handler
        await event_bus.publish(event)
        
        # Good handlers should still be called
        assert received.count("good") == 2
    
    @pytest.mark.asyncio
    async def test_error_handler(self, event_bus):
        """Test error handler registration."""
        errors = []
        
        async def error_handler(event, error):
            errors.append((event, error))
        
        event_bus.on_error(error_handler)
        
        async def bad_handler(event):
            raise ValueError("Test error")
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, bad_handler)
        
        event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="test-123",
            version=1,
        )
        
        await event_bus.publish(event)
        
        assert len(errors) == 1
        assert isinstance(errors[0][1], ValueError)
    
    @pytest.mark.asyncio
    async def test_get_subscriber_count(self, event_bus):
        """Test subscriber count."""
        async def handler1(event): pass
        async def handler2(event): pass
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, handler1)
        event_bus.subscribe(EventType.PHASE_COMPLETED, handler2)
        
        assert event_bus.get_subscriber_count(EventType.PHASE_COMPLETED) == 2
    
    @pytest.mark.asyncio
    async def test_total_subscribers(self, event_bus):
        """Test total subscriber count."""
        async def handler1(event): pass
        async def handler2(event): pass
        async def global_handler(event): pass
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, handler1)
        event_bus.subscribe(EventType.PHASE_STARTED, handler2)
        event_bus.subscribe_all(global_handler)
        
        assert event_bus.total_subscribers == 3
    
    @pytest.mark.asyncio
    async def test_clear(self, event_bus):
        """Test clearing all subscriptions."""
        async def handler(event): pass
        
        event_bus.subscribe(EventType.PHASE_COMPLETED, handler)
        event_bus.subscribe_all(handler)
        
        assert event_bus.total_subscribers > 0
        
        event_bus.clear()
        
        assert event_bus.total_subscribers == 0


class TestEventDecorators:
    """Tests for event handler decorators."""
    
    @pytest.mark.asyncio
    async def test_handle_event_decorator(self):
        """Test @handle_event decorator."""
        reset_event_bus()
        received = []
        
        @handle_event(EventType.PHASE_COMPLETED)
        async def on_phase_completed(event):
            received.append(event)
        
        bus = get_event_bus()
        event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="test-123",
            version=1,
        )
        
        await bus.publish(event)
        
        assert len(received) == 1
        
        reset_event_bus()
    
    @pytest.mark.asyncio
    async def test_handle_all_events_decorator(self):
        """Test @handle_all_events decorator."""
        reset_event_bus()
        received = []
        
        @handle_all_events()
        async def on_any_event(event):
            received.append(event.event_type)
        
        bus = get_event_bus()
        
        for event_type in [EventType.PHASE_STARTED, EventType.PHASE_COMPLETED]:
            event = make_event(event_type, aggregate_id="test", version=1)
            await bus.publish(event)
        
        assert EventType.PHASE_STARTED in received
        assert EventType.PHASE_COMPLETED in received
        
        reset_event_bus()


class TestGlobalEventBus:
    """Tests for global event bus instance."""
    
    def test_get_event_bus_singleton(self):
        """Test that get_event_bus returns singleton."""
        reset_event_bus()
        
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        
        assert bus1 is bus2
        
        reset_event_bus()
    
    def test_reset_event_bus(self):
        """Test resetting global event bus."""
        reset_event_bus()
        
        bus = get_event_bus()
        bus.subscribe(EventType.PHASE_COMPLETED, lambda e: None)
        
        assert bus.total_subscribers > 0
        
        reset_event_bus()
        
        new_bus = get_event_bus()
        assert new_bus.total_subscribers == 0

    def test_reset_event_bus_clears_all_handlers(self):
        """Test that reset clears typed, global, and error handlers."""
        reset_event_bus()
        bus = get_event_bus()

        bus.subscribe(EventType.PHASE_COMPLETED, lambda e: None)
        bus.subscribe_all(lambda e: None)
        bus.on_error(lambda e, err: None)

        assert bus.total_subscribers > 0

        reset_event_bus()
        fresh = get_event_bus()
        assert fresh.total_subscribers == 0

    def test_get_event_bus_returns_fresh_instance_after_reset(self):
        """Test that get_event_bus() creates a new instance after reset."""
        reset_event_bus()
        bus1 = get_event_bus()
        bus1.subscribe(EventType.PHASE_COMPLETED, lambda e: None)

        reset_event_bus()
        bus2 = get_event_bus()

        assert bus1 is not bus2
        assert bus2.total_subscribers == 0
