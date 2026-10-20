"""The event bus drains on stop, and a failing subscriber stalls only itself (OPS-2).

stop() cleared _running before drain(), so the consumer left its loop and every
queued event was dropped. The single consumer ran each handler's retries and
backoff before taking the next event, so one failing subscriber delayed every
other one. See docs/plans/audit-remediation-2026-10-20.md, OPS-2.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from reasoner.application.event_bus.bus import EventBus
from reasoner.core.events.domain_events import DomainEvent, EventType


def _event(i: int) -> DomainEvent:
    return DomainEvent(
        event_id=f"evt-{i}", event_type=EventType.RESEARCH_STEP_EMITTED,
        aggregate_id="run-1", version=1, timestamp=1704067200.0,
    )


@pytest.mark.asyncio
async def test_events_queued_at_stop_are_all_processed():
    bus = EventBus()
    bus._dead_letter_enabled = False
    await bus.start()
    seen: list[str] = []

    async def handler(event):
        await asyncio.sleep(0.01)
        seen.append(event.event_id)

    bus.subscribe(EventType.RESEARCH_STEP_EMITTED, handler)
    for i in range(20):
        await bus.publish(_event(i))
    await bus.stop()

    assert seen == [f"evt-{i}" for i in range(20)], "every event, in order"


@pytest.mark.asyncio
async def test_events_left_at_the_drain_timeout_are_dead_lettered(monkeypatch):
    bus = EventBus()
    await bus.start()
    dead: list[str] = []

    async def _dead_letter(event, error_message, handler_name=""):
        dead.append(event.event_id)

    monkeypatch.setattr(bus, "_log_to_dead_letter", _dead_letter)
    release = asyncio.Event()

    async def stuck(event):
        await release.wait()

    bus.subscribe(EventType.RESEARCH_STEP_EMITTED, stuck)
    for i in range(3):
        await bus.publish(_event(i))
    await asyncio.sleep(0.05)
    await bus.drain(timeout=0.2)

    assert dead == ["evt-1", "evt-2"], "the in-flight event finishes; the rest are recorded"
    release.set()
    await bus.stop()


@pytest.mark.asyncio
async def test_a_failing_subscriber_does_not_delay_another(monkeypatch):
    bus = EventBus()
    bus._dead_letter_enabled = False
    await bus.start()
    delivered: dict[str, float] = {}

    async def failing(event):
        raise RuntimeError("subscriber down")  # retried with 1s, 2s, 4s backoff

    async def healthy(event):
        delivered[event.event_id] = time.monotonic()

    bus.subscribe(EventType.RESEARCH_STEP_EMITTED, failing)
    bus.subscribe(EventType.RESEARCH_STEP_EMITTED, healthy)
    start = time.monotonic()
    await bus.publish(_event(1))
    await bus.publish(_event(2))
    await asyncio.sleep(0.3)

    assert set(delivered) == {"evt-1", "evt-2"}
    assert max(delivered.values()) - start < 0.25
    # Not stop(): it would wait out the failing handler's retries.
    tasks = [t for _, t in bus._lanes.values()] + [bus._worker_task]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
