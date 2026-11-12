"""Unsettled-run Port: a durable record of a run that was served but not billed.

A run is billed after it streams. When settlement fails (the ledger is down, or the
15 s settle timeout fires) the answer is already delivered, so the cost cannot be
refused, only recovered. The record cannot live in the ledger database: that is the
thing that failed. It goes to a store that fails independently, and an admin
replays it once the ledger is back (``UnsettledRunReplayService``).

Entries hold a ``user_id``, so the adapter bounds their age; see the adapter for the
retention period.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UnsettledRun:
    user_id: str
    reference_id: str
    cost_usd: float
    reserved_credits: int
    preset: str
    error: str
    recorded_at: float  # epoch seconds


class UnsettledRunPort(Protocol):
    async def record(self, run: UnsettledRun) -> None:
        """Store a run that could not be settled.

        A duplicate record is harmless: replay settles on ``reference_id``, which the
        ledger treats as an idempotency key.
        """
        ...

    async def list_pending(self, limit: int) -> list[UnsettledRun]:
        """Oldest first."""
        ...

    async def remove(self, run: UnsettledRun) -> None:
        """Drop a run once it has been settled."""
        ...
