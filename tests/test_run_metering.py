"""Metering is the only thing standing between an agent and free pipelines.

These tests pin the four behaviours that matter and that a refactor could
plausibly break: a completed run settles exactly once at the frame's own cost,
an abandoned run still settles the work already done, a ledger outage never
reaches the caller, and an unauthenticated run is never charged to anyone.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.run_metering import (
    RunContext,
    extract_run_cost,
    metered,
)

pytestmark = pytest.mark.unit


DONE = 'data: {"type": "done", "total_cost_usd": 0.0191, "errors": []}'
PHASE = 'data: {"type": "phase_complete", "phase": 2}'


class RecordingSink:
    """Test double for SettlementSink -- records, never charges."""

    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self.fail = fail

    async def settle(self, *, user_id, cost_usd, reference_id, preset) -> None:
        self.calls.append(
            {
                "user_id": user_id,
                "cost_usd": cost_usd,
                "reference_id": reference_id,
                "preset": preset,
            }
        )
        if self.fail:
            raise RuntimeError("ledger unavailable")


class RecordingObserver:
    def __init__(self):
        self.statuses: list[str] = []

    def observe(self, *, status: str) -> None:
        self.statuses.append(status)


async def frames(*items: str):
    for item in items:
        yield item


def user_ctx(**overrides) -> RunContext:
    return RunContext(
        preset="auto-budget",
        reference_id="run-1",
        user_id="user-42",
        tier="free",
        **overrides,
    )


# ── extract_run_cost ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "frame,expected",
    [
        ('data: {"type": "done", "total_cost_usd": 0.0123}', 0.0123),
        ('data: {"type": "done", "total_cost_usd": 2}', 2.0),
        # Only the terminal frame carries a settleable cost.
        ('data: {"type": "phase_complete", "total_cost_usd": 0.5}', None),
        # Free and refunded-to-zero runs must not produce a charge.
        ('data: {"type": "done", "total_cost_usd": 0}', None),
        ('data: {"type": "done", "total_cost_usd": -1}', None),
        ('data: {"type": "done", "total_cost_usd": true}', None),
        ('data: {"type": "done", "total_cost_usd": "0.5"}', None),
        # Malformed input must never break the stream the caller is reading.
        ("data: not json", None),
        ('data: ["done"]', None),
        (": keep-alive", None),
        ('{"type": "done", "total_cost_usd": 0.5}', None),
    ],
)
def test_cost_comes_only_from_a_terminal_done_frame(frame: str, expected):
    assert extract_run_cost(frame) == expected


# ── metered ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settles_once_at_the_cost_on_the_done_frame():
    sink = RecordingSink()

    seen = [f async for f in metered(frames(PHASE, DONE), user_ctx(), sink)]

    assert seen == [PHASE, DONE]
    assert sink.calls == [
        {
            "user_id": "user-42",
            "cost_usd": 0.0191,
            "reference_id": "run-1",
            "preset": "auto-budget",
        }
    ]


@pytest.mark.asyncio
async def test_frames_are_passed_through_untouched():
    """Metering observes; it must not rewrite what the caller reads."""
    sink = RecordingSink()
    originals = [PHASE, ": keep-alive", DONE]

    assert [f async for f in metered(frames(*originals), user_ctx(), sink)] == originals


@pytest.mark.asyncio
async def test_an_abandoned_stream_still_settles_the_work_already_done():
    """A client that hangs up after the done frame has still been served."""
    sink = RecordingSink()
    stream = metered(frames(PHASE, DONE, PHASE), user_ctx(), sink)

    collected = []
    async for frame in stream:
        collected.append(frame)
        if frame == DONE:
            break
    await stream.aclose()

    assert collected == [PHASE, DONE]
    assert len(sink.calls) == 1
    assert sink.calls[0]["cost_usd"] == 0.0191


@pytest.mark.asyncio
async def test_a_run_that_never_reported_a_cost_is_not_charged():
    sink = RecordingSink()

    await _drain(metered(frames(PHASE, PHASE), user_ctx(), sink))

    assert sink.calls == []


@pytest.mark.asyncio
async def test_an_anonymous_run_is_never_settled():
    """No account, nothing to charge -- and never a guess at whose it is."""
    sink = RecordingSink()
    ctx = RunContext(preset="auto-budget", reference_id="run-1", user_id=None)

    await _drain(metered(frames(DONE), ctx, sink))

    assert sink.calls == []


@pytest.mark.asyncio
async def test_a_ledger_failure_never_reaches_the_caller():
    """The answer is already delivered; a settlement outage is reconciled later."""
    sink = RecordingSink(fail=True)

    seen = [f async for f in metered(frames(DONE), user_ctx(), sink)]

    assert seen == [DONE]
    assert len(sink.calls) == 1


@pytest.mark.asyncio
async def test_a_failing_stream_settles_what_it_spent_and_still_raises():
    sink = RecordingSink()
    observer = RecordingObserver()

    async def exploding():
        yield DONE
        raise RuntimeError("provider died")

    with pytest.raises(RuntimeError, match="provider died"):
        await _drain(metered(exploding(), user_ctx(), sink, observer))

    assert len(sink.calls) == 1
    assert observer.statuses == ["error"]


@pytest.mark.asyncio
async def test_observer_records_success_for_a_clean_run():
    observer = RecordingObserver()

    await _drain(metered(frames(PHASE, DONE), user_ctx(), RecordingSink(), observer))

    assert observer.statuses == ["success"]


@pytest.mark.asyncio
async def test_a_broken_observer_does_not_break_the_run():
    class Exploding:
        def observe(self, *, status: str) -> None:
            raise RuntimeError("prometheus down")

    seen = [f async for f in metered(frames(DONE), user_ctx(), RecordingSink(), Exploding())]

    assert seen == [DONE]


async def _drain(stream) -> None:
    async for _ in stream:
        pass
