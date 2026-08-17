"""Metering wrapper shared by every inbound adapter that runs a pipeline.

A run is billed post-paid, from the ``total_cost_usd`` on its terminal ``done``
frame, so metering is naturally a *wrapper around the stream* rather than a step
before or after it.

Keeping it here rather than in the HTTP layer is what stops a second adapter --
the sync endpoint, an MCP tool -- from quietly running pipelines for free: an
adapter composes :func:`metered` around the generator it already has and gets
settlement, disconnect handling, and metrics without knowing how any of them
work.

The frame-level logic is pure (:func:`extract_run_cost`); the effects arrive as
injected protocols, so tests exercise the whole path without a ledger.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

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

    async def release(
        self,
        *,
        user_id: str,
        credits: int,
        reference_id: str,
    ) -> None:
        """Return credits from a reservation that won't be (fully) used."""
        ...

    async def settle(
        self,
        *,
        user_id: str,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None: ...


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


def extract_run_cost(frame: str) -> float | None:
    """Pull ``total_cost_usd`` out of a terminal ``done`` SSE frame.

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
    if not isinstance(event, dict) or event.get("type") != "done":
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

    Settlement happens in ``finally`` so a client that disconnects mid-run is
    still charged for the work already performed, and it never raises: the
    answer has been delivered, so a ledger outage is reconciled later rather
    than surfaced to a caller who can do nothing about it.
    """
    cost_usd = 0.0
    has_error = False
    try:
        async for frame in stream:
            cost_usd = extract_run_cost(frame) or cost_usd
            yield frame
    except Exception:
        has_error = True
        raise
    finally:
        if ctx.user_id and ctx.reserved_credits > 0:
            await _true_up(sink, ctx, cost_usd)
        elif ctx.user_id and cost_usd > 0:
            # Defensive fallback for a caller that never reserved. Every
            # production call site reserves via reserve_run_budget(); this
            # keeps older/uninstrumented callers billed rather than free.
            await _settle(sink, ctx, cost_usd)
        if observer is not None:
            try:
                observer.observe(status="error" if has_error else "success")
            except Exception as exc:
                logger.warning("Run observer failed for %s: %s", ctx.reference_id, exc)


async def _true_up(sink: SettlementSink, ctx: RunContext, cost_usd: float) -> None:
    """Release the held reservation, then charge the actual cost.

    Two ledger entries through the existing composable primitives rather
    than new delta arithmetic -- release is exempt from the same fail-soft
    handling as settle so one failure doesn't block the other.
    """
    try:
        await sink.release(
            user_id=ctx.user_id or "",
            credits=ctx.reserved_credits,
            reference_id=f"{ctx.reference_id}:release",
        )
    except Exception as exc:
        logger.warning(
            "Reservation release failed for user %s run %s (%d credits): %s",
            ctx.user_id, ctx.reference_id, ctx.reserved_credits, exc,
        )
    if cost_usd > 0:
        await _settle(sink, ctx, cost_usd)


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
    "SettlementSink",
    "extract_run_cost",
    "metered",
    "reserve_run_budget",
]
