"""RUN-9: a failed event-store write must not advance the aggregate version.

`_persist_event` swallows a failed save (an event-store outage must not break
the run), but `RunStream.persist` incremented `event_version` regardless. The
stored versions then skipped a number, and `PipelineAggregate.apply` raises on
the gap, so that run could never be loaded again.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reasoner.api.execution.sse_observer import RunStream
from reasoner.core.events.domain_events import EventType

pytestmark = pytest.mark.unit

_GET_STORE = "reasoner.infrastructure.persistence.event_store.get_event_store"


class _FlakyStore:
    """Fails the save of one event type, once; records what it did store."""

    def __init__(self, fail_on: EventType | None) -> None:
        self.fail_on = fail_on
        self.saved: list[tuple[EventType, int]] = []

    async def save_events(self, events) -> None:
        for event in events:
            if event.event_type == self.fail_on:
                self.fail_on = None  # fail once
                raise ConnectionError("event store down")
            self.saved.append((event.event_type, event.version))


async def _noop(_payload) -> None:
    return None


def _stream() -> RunStream:
    return RunStream("run-1", _noop, lambda _p: None)


async def _started(stream: RunStream) -> None:
    await stream.persist(
        EventType.PIPELINE_STARTED, problem="p", preset="x", method="m", options={}
    )


async def _failed(stream: RunStream) -> None:
    await stream.persist(
        EventType.PIPELINE_FAILED, error="e", phase_at_failure=0, phases_completed=0
    )


async def test_failed_save_leaves_no_version_gap() -> None:
    store = _FlakyStore(fail_on=EventType.PIPELINE_STARTED)
    stream = _stream()
    with patch(_GET_STORE, return_value=store):
        await _started(stream)
        await _failed(stream)

    # The first event is lost, not the sequence: the next one reuses version 1.
    assert store.saved == [(EventType.PIPELINE_FAILED, 1)]
    assert stream.event_version == 2


async def test_successful_saves_stay_contiguous() -> None:
    store = _FlakyStore(fail_on=None)
    stream = _stream()
    with patch(_GET_STORE, return_value=store):
        await _started(stream)
        await _failed(stream)

    assert [v for _, v in store.saved] == [1, 2]
