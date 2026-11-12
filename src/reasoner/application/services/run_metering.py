"""Metering wrapper shared by every inbound adapter that runs a pipeline.

A run is billed post-paid, from the ``total_cost_usd`` carried on its
``phase_complete`` frames and finalised on the terminal ``done`` frame, so
metering is naturally a *wrapper around the stream* rather than a step before or
after it.

Keeping it here rather than in the HTTP layer is what stops a second adapter --
the sync endpoint, an MCP tool -- from quietly running pipelines for free: an
adapter composes :func:`metered` around the generator it already has and gets
settlement, disconnect handling, and metrics without knowing how any of them
work.

The frame-level logic is pure (:func:`extract_run_cost`); the effects arrive as
injected protocols, so tests exercise the whole path without a ledger.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import weakref
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import anyio

from reasoner.application.services.anonymous_trial_policy import (
    AnonymousTrialCharge,
    refund_anonymous_trial,
)
from reasoner.core.constants_limits import SETTLE_TIMEOUT_SECONDS
from reasoner.core.degrade import degraded

logger = logging.getLogger(__name__)

SSE_DATA_PREFIX = "data: "


class SettlementSink(Protocol):
    """Reserves a run's estimated cost up front, then charges what it
    actually spent."""

    async def reserve(
        self,
        *,
        user_id: str,
        estimated_cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> int:
        """Hold estimated credits against the balance before a run starts.

        Returns the number of credits reserved (0 for a free/zero estimate).
        Raises InsufficientCreditsError -- callers must fail closed, not
        start the run.
        """
        ...

    async def settle(
        self,
        *,
        user_id: str,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None: ...

    async def true_up(
        self,
        *,
        user_id: str,
        reserved_credits: int,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None:
        """Release the reservation and charge the real cost as one transaction.

        Either both ledger rows land or neither does, so a failure cannot leave a
        refunded run with no charge.
        """
        ...

    async def record_unsettled(
        self,
        *,
        user_id: str,
        reference_id: str,
        cost_usd: float,
        reserved_credits: int,
        preset: str,
        error: str,
    ) -> None:
        """Durably note a run whose settlement failed, so it can be replayed."""
        ...

    async def release_quota_slot(
        self, *, user_id: str, claimed_at: datetime | None = None
    ) -> None:
        """Give back the quota slot admission took, for a run that cost nothing.

        ``claimed_at`` makes a release after the month reset a no-op (M4).
        """
        ...


class RunObserver(Protocol):
    """Records the outcome of a run for metrics."""

    def observe(self, *, status: str) -> None: ...


@dataclass(frozen=True)
class RunContext:
    """Who is running what, and through which door.

    ``user_id`` is None for anonymous and legacy-key callers: there is no
    account to charge, so settlement is skipped rather than guessed at.

    ``reserved_credits`` is set by :func:`reserve_run_budget` before the run
    starts. When it's non-zero, settlement is a true-up against the held
    reservation instead of a fresh charge.
    """

    preset: str
    reference_id: str
    user_id: str | None = None
    tier: str = "anonymous"
    interface: str = "web"
    reserved_credits: int = 0
    #: Set when :func:`metered` starts. A stream the client dropped before its
    #: first frame never runs ``metered``'s ``finally``, so the HTTP layer reads
    #: this to release that reservation itself.
    started: asyncio.Event | None = None
    #: The ``client_run_id`` claim (``idempotency.register_run``). Released when
    #: the run does not complete, so the caller can retry with the same id.
    run_claim: str | None = None
    #: Admission took a quota slot for this run (audit 6, finding 3). A run that
    #: ends up costing nothing gives it back; a billed run keeps it.
    quota_slot: bool = False
    #: Credits counted against an anonymous caller's daily cap at admission; given
    #: back when the run ends up costing nothing.
    anon_charge: AnonymousTrialCharge | None = field(default=None, compare=False)
    #: Built right after admission took the quota slot, so this stands in for the
    #: claim time: a release in a later quota period must not take from that one.
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC), compare=False)


@dataclass
class RunSpend:
    """Spend the pipeline knows about but has not yet put on a frame.

    ``metered`` bills from ``phase_complete``/``done`` frames, so a run cancelled
    mid-phase reported nothing and settled at $0 for tokens the providers had
    billed. The run task registers a live reader of its state's running total.
    It is read at settle time, not pushed on the way out: on a disconnect the
    stream cancels the run task without awaiting it (streaming.py), so a figure
    written in the task's ``finally`` lands after ``metered`` has settled.
    """

    source: Callable[[], float] | None = None

    def read(self) -> float:
        if self.source is None:
            return 0.0
        try:
            return float(self.source() or 0.0)
        except Exception as exc:  # a broken reader must not block settlement
            degraded("run_metering.spend_reader", None, exc=exc)
            return 0.0


_current_spend: contextvars.ContextVar[RunSpend | None] = contextvars.ContextVar(
    "run_spend", default=None
)


def track_run_spend(source: Callable[[], float]) -> None:
    """Let the enclosing :func:`metered` read the run's spend so far. No-op outside one."""
    spend = _current_spend.get()
    if spend is not None:
        spend.source = source


#: Frame types that carry a ``total_cost_usd``. ``done`` is the final figure;
#: ``phase_complete`` carries the running total so an abandoned run is billed
#: for what it actually spent rather than released in full.
COST_BEARING_FRAME_TYPES = frozenset({"done", "phase_complete"})


def extract_run_cost(frame: str) -> float | None:
    """Pull ``total_cost_usd`` out of a cost-bearing SSE frame.

    ``done`` carries the final cost; ``phase_complete`` carries the running
    total after each phase. Reading both is what lets a run abandoned
    mid-stream settle its incurred spend instead of releasing the whole
    reservation.

    Returns None for every other frame, including keep-alive comments and
    malformed payloads: a parsing problem must never break the stream the
    caller is reading.
    """
    if not frame.startswith(SSE_DATA_PREFIX):
        return None
    try:
        event = json.loads(frame[len(SSE_DATA_PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict) or event.get("type") not in COST_BEARING_FRAME_TYPES:
        return None
    # A cache replay re-sends the original run's cost frames. Billing them
    # charged the cached answer a second time (docs/plans/
    # audit-remediation-2026-10-20.md BIL-3).
    if event.get("cached"):
        return None
    cost = event.get("total_cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None
    return float(cost) if cost > 0 else None


async def metered(
    stream: AsyncIterator[str],
    ctx: RunContext,
    sink: SettlementSink,
    observer: RunObserver | None = None,
) -> AsyncIterator[str]:
    """Yield every frame untouched, then settle what the run actually cost.

    Settlement happens in ``finally`` so a client that hangs up *after* the
    terminal ``done`` frame is still charged, and it never raises: the answer
    has been delivered, so a ledger outage is reconciled later rather than
    surfaced to a caller who can do nothing about it.

    A run abandoned mid-stream is billed for the spend it already incurred.
    ``phase_complete`` frames carry a running ``total_cost_usd``, so the last
    one seen before the client hung up is settled and only the remainder of the
    reservation is released. Policy decision, 2026-09-03: the user pays for
    tokens actually spent, because the providers bill us for them whether or
    not anyone read the answer.

    A run that genuinely cost nothing -- a cache hit, or an abort before the
    first phase completed -- still releases the whole reservation, because
    ``cost_usd`` stays 0.0 and :func:`_true_up` skips the settle.
    """
    # release_unstarted already gave the claim and quota slot back: this
    # settlement must not release them a second time.
    released = ctx.started is not None and ctx.started in _unstarted_released
    if ctx.started is not None:
        ctx.started.set()
    cost_usd = 0.0
    has_error = False
    completed = False
    done_with_errors = False
    spend = RunSpend()
    _current_spend.set(spend)
    try:
        async for frame in stream:
            cost_usd = extract_run_cost(frame) or cost_usd
            done_errors = _done_has_errors(frame)
            if done_errors is not None:
                completed = True
                done_with_errors = done_errors
            yield frame
    except Exception:
        has_error = True
        raise
    finally:
        # The run task's own figure covers a run cut off before any cost frame.
        cost_usd = max(cost_usd, spend.read())
        # A client disconnect cancels this task, and Starlette's anyio scope
        # re-delivers that cancellation at every await, so an unshielded
        # settlement was interrupted and neither the release nor the true-up
        # ran (docs/plans/audit-remediation-2-2026-10-20.md BIL-12).
        with anyio.CancelScope(shield=True):
            try:
                with anyio.fail_after(SETTLE_TIMEOUT_SECONDS):
                    await _finalize(sink, ctx, cost_usd)
            except TimeoutError as exc:
                degraded(
                    "run_metering.settle_timeout", None, exc=exc,
                    detail=f"run {ctx.reference_id} left unsettled (${cost_usd:.6f})",
                )
                # The interrupted write may or may not have landed; replay is
                # idempotent on reference_id, so recording it is always safe.
                await _record_unsettled(sink, ctx, cost_usd, exc)
            if cost_usd <= 0 and not released:
                # Once, here: a free run keeps no slot and none of its trial credits.
                with anyio.move_on_after(SETTLE_TIMEOUT_SECONDS):
                    await _release_quota_slot(sink, ctx)
                    await refund_anonymous_trial(ctx.anon_charge)
            # Only a run that spent nothing can be retried under the same id: a
            # run that spent and stopped short keeps its claim, or the retry
            # would bill the same work again.
            if not released:
                if cost_usd <= 0 and (not completed or done_with_errors):
                    await _release_claim(ctx)
                else:  # kept: a duplicate is told the run finished, not that it is live
                    await _complete_claim(ctx)
        if observer is not None:
            try:
                observer.observe(status="error" if has_error else "success")
            except Exception as exc:
                logger.warning("Run observer failed for %s: %s", ctx.reference_id, exc)


async def _finalize(sink: SettlementSink, ctx: RunContext, cost_usd: float) -> None:
    if ctx.user_id and ctx.reserved_credits > 0:
        await _true_up(sink, ctx, cost_usd)
    elif ctx.user_id and cost_usd > 0:
        # Defensive fallback for a caller that never reserved. Every
        # production call site reserves via reserve_run_budget(); this
        # keeps older/uninstrumented callers billed rather than free.
        await _settle(sink, ctx, cost_usd)


async def _release_quota_slot(sink: SettlementSink, ctx: RunContext) -> None:
    """Give back the admission quota slot of a run that was not billed. Never raises."""
    if not ctx.quota_slot or not ctx.user_id:
        return
    try:
        await sink.release_quota_slot(user_id=ctx.user_id, claimed_at=ctx.created_at)
    except Exception as exc:
        logger.warning(
            "Quota slot release failed for user %s run %s: %s", ctx.user_id, ctx.reference_id, exc
        )


# Events of contexts release_unstarted has settled. Not `started` itself:
# callers read that to decide whether the stream ever ran.
_unstarted_released: weakref.WeakSet[asyncio.Event] = weakref.WeakSet()


async def release_unstarted(sink: SettlementSink, ctx: RunContext) -> None:
    """Release the reservation of a stream that never started.

    A client that drops before the first frame never enters :func:`metered`,
    so its ``finally`` never runs and the hold would stay debited forever.
    """
    if ctx.started is None or ctx.started.is_set():
        return
    with anyio.CancelScope(shield=True):
        with anyio.move_on_after(SETTLE_TIMEOUT_SECONDS) as scope:
            if ctx.user_id and ctx.reserved_credits > 0:
                await _true_up(sink, ctx, 0.0)
            await _release_quota_slot(sink, ctx)
            await _release_claim(ctx)
        _unstarted_released.add(ctx.started)
        if scope.cancelled_caught:
            # A timed-out release left the hold debited with no record of it;
            # replay is idempotent on reference_id, so recording is always safe.
            await _record_unsettled(sink, ctx, 0.0, TimeoutError("release_unstarted timed out"))


def _done_has_errors(frame: str) -> bool | None:
    """None for any frame but the terminal ``done``; else whether it reports errors."""
    if not frame.startswith(SSE_DATA_PREFIX):
        return None
    try:
        event = json.loads(frame[len(SSE_DATA_PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict) or event.get("type") != "done":
        return None
    return bool(event.get("errors"))


async def _release_claim(ctx: RunContext) -> None:
    # Module lookup at call time so tests can patch it.
    from reasoner.application.services import idempotency

    await idempotency.release_run(ctx.run_claim)


async def _complete_claim(ctx: RunContext) -> None:
    from reasoner.application.services import idempotency

    await idempotency.complete_run(ctx.run_claim)


async def _true_up(sink: SettlementSink, ctx: RunContext, cost_usd: float) -> None:
    """Give back the held reservation and charge the actual cost, in one transaction.

    Two ledger rows (``<ref>:release`` and ``<ref>``) written together: a failure
    between two separate writes left the refund in and the charge out, a free run.
    If the transaction fails, neither row lands, so the reservation stays debited
    (the user pays the estimate, the safe side) and the run is recorded for replay.
    """
    try:
        await sink.true_up(
            user_id=ctx.user_id or "",
            reserved_credits=ctx.reserved_credits,
            cost_usd=cost_usd,
            reference_id=ctx.reference_id,
            preset=ctx.preset,
        )
    except Exception as exc:
        logger.warning(
            "Credit true-up failed for user %s run %s (%d reserved, $%.6f): %s",
            ctx.user_id, ctx.reference_id, ctx.reserved_credits, cost_usd, exc,
        )
        await _record_unsettled(sink, ctx, cost_usd, exc)


async def _settle(sink: SettlementSink, ctx: RunContext, cost_usd: float) -> None:
    try:
        await sink.settle(
            user_id=ctx.user_id or "",
            cost_usd=cost_usd,
            reference_id=ctx.reference_id,
            preset=ctx.preset,
        )
    except Exception as exc:
        logger.warning(
            "Credit settlement failed for user %s run %s ($%.6f): %s",
            ctx.user_id,
            ctx.reference_id,
            cost_usd,
            exc,
        )
        await _record_unsettled(sink, ctx, cost_usd, exc)


async def _record_unsettled(
    sink: SettlementSink, ctx: RunContext, cost_usd: float, exc: BaseException
) -> None:
    """Note a run that was served but not settled. Never raises.

    The answer is already delivered, so there is nothing to refuse; the record is
    what makes "reconciled later" true. If the sink cannot store it either, the
    ERROR line below is the last copy, with every field a replay needs.
    """
    if not ctx.user_id or (ctx.reserved_credits <= 0 and cost_usd <= 0):
        return  # nothing was held and nothing is owed
    try:
        await sink.record_unsettled(
            user_id=ctx.user_id,
            reference_id=ctx.reference_id,
            cost_usd=cost_usd,
            reserved_credits=ctx.reserved_credits,
            preset=ctx.preset,
            error=repr(exc),
        )
    except Exception as record_exc:
        logger.error(
            "UNSETTLED RUN NOT RECORDED (%s): user=%s reference=%s cost_usd=%.6f "
            "reserved_credits=%d preset=%s error=%s",
            record_exc, ctx.user_id, ctx.reference_id, cost_usd,
            ctx.reserved_credits, ctx.preset, exc,
        )


async def reserve_run_budget(
    *,
    user_id: str | None,
    preset: str,
    problem: str,
    reference_id: str,
    sink: SettlementSink,
) -> int:
    """Reserve estimated credits for a run before it starts.

    Returns 0 for anonymous callers (nothing to reserve against -- capped
    separately by AnonymousTrialPolicy) or a free estimate. Raises
    InsufficientCreditsError to fail closed: the caller must not start the
    run, and should translate this into a 402 response.
    """
    if not user_id:
        return 0
    from reasoner.application.services.estimate_service import estimate_cost

    estimate = await estimate_cost(problem, preset)
    return await sink.reserve(
        user_id=user_id,
        estimated_cost_usd=estimate["estimated_cost_usd"],
        reference_id=f"{reference_id}:reserve",
        preset=preset,
    )


__all__ = [
    "RunContext",
    "RunObserver",
    "RunSpend",
    "SettlementSink",
    "COST_BEARING_FRAME_TYPES",
    "extract_run_cost",
    "metered",
    "track_run_spend",
    "release_unstarted",
    "reserve_run_budget",
]
