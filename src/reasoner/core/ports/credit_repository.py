"""Port: persistence contract for the credit ledger.

Implementations live in ``reasoner.infrastructure.persistence``. The
application layer depends on this protocol only, never on asyncpg.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reasoner.domain.credits import CreditBalance, CreditLedgerEntry, CreditReason


@runtime_checkable
class CreditRepository(Protocol):
    """Atomic credit storage."""

    async def get_balance(self, user_id: str) -> CreditBalance:
        """Return the user's balance, creating a zeroed row if none exists."""
        ...

    async def record(
        self,
        user_id: str,
        delta: int,
        reason: CreditReason,
        reference_id: str | None = None,
        description: str | None = None,
        allow_overdraft: bool = False,
    ) -> CreditLedgerEntry:
        """Apply ``delta`` to the balance and append a ledger entry atomically.

        Must be a single transaction with the balance row locked, so concurrent
        runs cannot both read the same balance and double-spend it.

        ``reference_id`` is an idempotency key scoped to the user: replaying the
        same reference must return the original entry without moving the balance.

        Raises:
            InsufficientCreditsError: when the charge would breach the overdraft
                floor and ``allow_overdraft`` is False.
        """
        ...

    async def list_entries(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreditLedgerEntry]:
        """Return ledger entries newest-first."""
        ...

    async def grant_monthly_allowance(
        self,
        user_id: str,
        credits: int,
        period_key: str,
    ) -> CreditLedgerEntry | None:
        """Grant a period's allowance exactly once.

        ``period_key`` (e.g. ``"2026-08"``) makes the grant idempotent; returns
        None when this period was already granted.
        """
        ...
