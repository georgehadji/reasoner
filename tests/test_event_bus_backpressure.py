"""Tests for EventBus queue backpressure."""

from __future__ import annotations

import asyncio
import pytest

from reasoner.application.event_bus.bus import EventBus
from reasoner.core.events.domain_events import DomainEvent, EventType


@pytest.mark.asyncio
async def test_event_bus_drops_events_when_queue_full():
    """
    Publishing non-critical events faster than they are consumed must drop the
    excess rather than block the publisher.

    Two things the previous version got wrong: the handler has to be slow for the
    queue to fill at all (a fast handler drains as fast as the producer publishes),
    and the event type has to be non-critical — critical events deliberately apply
    backpressure by awaiting a slot instead of dropping.
    """
    bus = EventBus(max_queue_size=5)
    await bus.start()

    processed = 0
    release = asyncio.Event()

    async def slow_handler(event):
        nonlocal processed
        await release.wait()
        processed += 1

    bus.subscribe(EventType.PERSPECTIVE_GENERATED, slow_handler)

    # Publish well past the queue bound while the consumer is stalled.
    for i in range(50):
        event = DomainEvent(
            event_id=f"evt-{i}",
            event_type=EventType.PERSPECTIVE_GENERATED,
            aggregate_id=f"pipe-{i}",
            version=1,
            timestamp=1704067200.0,
        )
        await bus.publish(event)

    assert bus._dropped_event_count > 0, "expected non-critical events to be dropped"

    release.set()
    await asyncio.sleep(0.2)
    await bus.stop()

    # Never more than the queue ever held.
    assert processed < 50


@pytest.mark.asyncio
async def test_critical_events_are_not_dropped():
    """Critical events await a queue slot instead of being dropped.

    PHASE_COMPLETED and the billing events carry state the system cannot silently
    lose, so publish() applies backpressure for them rather than discarding.
    """
    bus = EventBus(max_queue_size=2)
    await bus.start()

    seen: list[str] = []

    async def handler(event):
        seen.append(event.event_id)

    bus.subscribe(EventType.PHASE_COMPLETED, handler)

    for i in range(20):
        await bus.publish(
            DomainEvent(
                event_id=f"crit-{i}",
                event_type=EventType.PHASE_COMPLETED,
                aggregate_id="pipe",
                version=1,
                timestamp=1704067200.0,
            )
        )

    await asyncio.sleep(0.2)
    await bus.stop()

    assert bus._dropped_event_count == 0
    assert len(seen) == 20
