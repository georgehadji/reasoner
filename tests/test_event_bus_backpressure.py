"""Tests for EventBus queue backpressure."""

from __future__ import annotations

import asyncio
import pytest

from reasoner.application.event_bus.bus import EventBus
from reasoner.core.events.domain_events import DomainEvent, EventType


@pytest.mark.asyncio
async def test_event_bus_drops_events_when_queue_full():
    """
    Publishing events to a bus with a small queue should drop
    events once the queue is full.
    """
    bus = EventBus(max_queue_size=5)
    await bus.start()

    processed = 0

    async def fast_handler(event):
        nonlocal processed
        processed += 1

    bus.subscribe(EventType.PHASE_COMPLETED, fast_handler)

    # Publish 10 events quickly
    for i in range(10):
        event = DomainEvent(
            event_id=f"evt-{i}",
            event_type=EventType.PHASE_COMPLETED,
            aggregate_id=f"pipe-{i}",
            version=1,
            timestamp=1704067200.0,
        )
        await bus.publish(event)

    # Give the worker a moment to drain the queue
    await asyncio.sleep(0.2)
    await bus.stop()

    # Queue max size is 5, so at most 5 events should have been queued.
    # Some may have been processed already.
    assert processed <= 5
