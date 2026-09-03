"""Metering is the only thing standing between an agent and free pipelines.

These tests pin the five behaviours that matter and that a refactor could
plausibly break: a completed run settles exactly once at the frame's own cost,
a client that hangs up *after* the done frame still settles it, a client that
abandons the run *before* done settles what the run actually spent (policy
decision, 2026-09-03: the user pays for tokens already spent, since the
providers bill us for them regardless), a ledger outage never reaches the
caller, and an unauthenticated run is never charged to anyone.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.run_metering import (
    COST_BEARING_FRAME_TYPES,
    RunContext,
    extract_run_cost,
    metered,
    reserve_run_budget,
)

pytestmark = pytest.mark.unit


DONE = 'data: {"type": "done", "total_cost_usd": 0.0191, "errors": []}'
PHASE = 'data: {"type": "phase_complete", "phase": 2}'
# A phase_complete frame carrying the running cost, as pipeline.py:596 emits.
PHASE_1 = 'data: {"type": "phase_complete", "phase": 1, "total_cost_usd": 0.004}'
PHASE_2 = 'data: {"type": "phase_complete", "phase": 2, "total_cost_usd": 0.009}'


class RecordingSink:
    """Test double for SettlementSink -- records, never charges."""

    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self.reserve_calls: list[dict] = []
        self.release_calls: list[dict] = []
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

    async def reserve(self, *, user_id, estimated_cost_usd, reference_id, preset) -> int:
        self.reserve_calls.append(
            {
                "user_id": user_id,
                "estimated_cost_usd": estimated_cost_usd,
                "reference_id": reference_id,
                "preset": preset,
            }
        )
        return 20  # arbitrary fixed reservation for tests that don't care about the exact amount

    async def release(self, *, user_id, credits, reference_id) -> None:
        self.release_calls.append(
            {"user_id": user_id, "credits": credits, "reference_id": reference_id}
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
        # phase_complete is cost-bearing too: it is what lets an abandoned
        # run settle what it actually spent instead of releasing in full.
        ('data: {"type": "phase_complete", "total_cost_usd": 0.5}', 0.5),
        # Frame types that carry no cost, even if one were smuggled in.
        ('data: {"type": "phase_error", "total_cost_usd": 0.5}', None),
        ('data: {"type": "cancelled", "total_cost_usd": 0.5}', None),
        ('data: {"type": "connecting"}', None),
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
def test_cost_comes_only_from_a_cost_bearing_frame(frame: str, expected):
    assert extract_run_cost(frame) == expected


def test_cost_bearing_frame_types_is_exactly_done_and_phase_complete():
    # Pins the set itself, not just extract_run_cost's behaviour on a sample:
    # a third type added here without a corresponding emitter is a silent
    # billing hole, and one removed here is a silent double-release.
    assert COST_BEARING_FRAME_TYPES == frozenset({"done", "phase_complete"})


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


# ── reservation / true-up ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_reserved_run_releases_the_reservation_and_settles_actual_cost():
    """True-up: two ledger entries (release then settle), not one delta --
    proves both legs of the composition, not just that *a* charge happened."""
    sink = RecordingSink()
    ctx = user_ctx(reserved_credits=20)

    await _drain(metered(frames(DONE), ctx, sink))

    assert sink.release_calls == [
        {"user_id": "user-42", "credits": 20, "reference_id": "run-1:release"}
    ]
    assert sink.calls == [
        {"user_id": "user-42", "cost_usd": 0.0191, "reference_id": "run-1", "preset": "auto-budget"}
    ]


@pytest.mark.asyncio
async def test_a_reserved_run_that_cost_nothing_still_releases_the_reservation():
    """A cache hit or an abandoned run with no reported spend returns the
    whole hold, not just the part matching the (zero) actual cost."""
    sink = RecordingSink()
    ctx = user_ctx(reserved_credits=20)

    await _drain(metered(frames(PHASE), ctx, sink))

    assert sink.release_calls == [
        {"user_id": "user-42", "credits": 20, "reference_id": "run-1:release"}
    ]
    assert sink.calls == []  # no settle call for zero cost


@pytest.mark.asyncio
async def test_a_run_abandoned_mid_stream_is_billed_for_what_it_spent():
    """The policy this closes (2026-09-03): a run abandoned before the
    terminal ``done`` frame is billed for tokens already spent, not released
    in full. The provider charges us for those tokens whether or not the
    client stayed connected to read the answer.

    The client disconnects after phase 2, never seeing a ``done`` frame --
    generator.aclose() is exactly what an ASGI server does when a request
    disconnects mid-stream, so this reproduces the real abandonment path
    rather than asserting on cost accounting in the abstract.
    """
    sink = RecordingSink()
    ctx = user_ctx(reserved_credits=20)
    stream = metered(frames(PHASE_1, PHASE_2), ctx, sink)

    seen = [await stream.__anext__(), await stream.__anext__()]
    await stream.aclose()

    assert seen == [PHASE_1, PHASE_2]
    # True-up releases the whole hold and settles the actual cost as two
    # entries (see _true_up's docstring), the same shape the completed-run
    # case uses -- the fix is which cost reaches this call, not the shape.
    assert sink.release_calls == [
        {"user_id": "user-42", "credits": 20, "reference_id": "run-1:release"}
    ]
    assert sink.calls == [
        {"user_id": "user-42", "cost_usd": 0.009, "reference_id": "run-1", "preset": "auto-budget"}
    ]


@pytest.mark.asyncio
async def test_the_running_cost_used_on_abandonment_is_the_latest_seen():
    """Guards against billing a superseded figure: if a later phase reports a
    lower running total (a refund folded into the state, a correction), the
    charge must track the most recent frame, not accumulate or use the first."""
    sink = RecordingSink()
    ctx = user_ctx(reserved_credits=20)

    await _drain(metered(frames(PHASE_2, PHASE_1), ctx, sink))

    assert sink.calls == [
        {"user_id": "user-42", "cost_usd": 0.004, "reference_id": "run-1", "preset": "auto-budget"}
    ]


@pytest.mark.asyncio
async def test_release_failure_does_not_block_settlement():
    """The release and the settle are independent ledger entries -- one
    failing (e.g. a transient ledger error) must not silently skip the
    other and let a real charge go unbilled."""
    sink = RecordingSink(fail=True)
    ctx = user_ctx(reserved_credits=20)

    seen = [f async for f in metered(frames(DONE), ctx, sink)]

    assert seen == [DONE]
    assert len(sink.release_calls) == 1  # attempted, even though it raised
    assert len(sink.calls) == 1  # settle still ran despite the release failing


@pytest.mark.asyncio
async def test_unreserved_authenticated_run_still_settles_flat():
    """Backward-compat fallback: reserved_credits defaults to 0, so a caller
    that hasn't been updated to reserve still gets billed, not a free run."""
    sink = RecordingSink()

    await _drain(metered(frames(DONE), user_ctx(), sink))  # reserved_credits=0 by default

    assert sink.release_calls == []
    assert len(sink.calls) == 1


@pytest.mark.asyncio
async def test_reserve_run_budget_returns_zero_for_anonymous_callers():
    sink = RecordingSink()

    reserved = await reserve_run_budget(
        user_id=None, preset="auto-budget", problem="hello", reference_id="run-1", sink=sink,
    )

    assert reserved == 0
    assert sink.reserve_calls == []


@pytest.mark.asyncio
async def test_reserve_run_budget_calls_sink_with_a_reserve_scoped_reference_id():
    sink = RecordingSink()

    reserved = await reserve_run_budget(
        user_id="user-42", preset="auto-budget", problem="hello world", reference_id="run-1", sink=sink,
    )

    assert reserved == 20  # RecordingSink's fixed stub reservation
    assert len(sink.reserve_calls) == 1
    call = sink.reserve_calls[0]
    assert call["user_id"] == "user-42"
    assert call["reference_id"] == "run-1:reserve"
    assert call["estimated_cost_usd"] > 0


@pytest.mark.asyncio
async def test_reserve_run_budget_propagates_insufficient_credits():
    from reasoner.domain.credits import InsufficientCreditsError

    class RefusingSink(RecordingSink):
        async def reserve(self, *, user_id, estimated_cost_usd, reference_id, preset) -> int:
            raise InsufficientCreditsError(required=100, available=5)

    with pytest.raises(InsufficientCreditsError):
        await reserve_run_budget(
            user_id="user-42", preset="auto-budget", problem="hello",
            reference_id="run-1", sink=RefusingSink(),
        )


# ── concurrency: the actual race the plan flags ─────────────────────


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_overspend_a_balance():
    """The real-world bug: two runs starting at once must not both pass an
    affordability check sized for only one of them. Exercises the real
    CreditService + InMemoryCreditRepository (asyncio.Lock-guarded), not
    just this module's thin wrapper -- the atomicity guarantee actually
    lives in the repository, so a fake sink can't prove this closed.
    """
    import asyncio
    import uuid

    from reasoner.application.services.credit_service import CreditService
    from reasoner.domain.credits import CreditReason, InsufficientCreditsError
    from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

    repo = InMemoryCreditRepository()
    service = CreditService(repo)
    user_id = str(uuid.uuid4())
    await service.grant(user_id, 10, reason=CreditReason.SIGNUP_BONUS)

    async def try_charge(ref: str):
        try:
            await repo.record(
                user_id, delta=-6, reason=CreditReason.PIPELINE_RUN,
                reference_id=ref, allow_overdraft=False,
            )
            return "ok"
        except InsufficientCreditsError:
            return "rejected"

    results = await asyncio.gather(try_charge("run-a:reserve"), try_charge("run-b:reserve"))

    # Balance is 10; each charge wants 6. Both cannot fit -- exactly one
    # must succeed and the other must be rejected, never both accepted.
    assert sorted(results) == ["ok", "rejected"]
    final_balance = await service.get_balance(user_id)
    assert final_balance.balance == 4  # 10 - 6, the rejected charge left no trace
