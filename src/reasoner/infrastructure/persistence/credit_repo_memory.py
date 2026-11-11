"""
In-memory CreditRepository — for tests and single-process local development.

Balances live in the process, so this is never appropriate for production:
the service factory only selects it outside production environments.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from reasoner.core.ports.credit_repository import CreditRepository
from reasoner.domain.credits import (
    CreditBalance,
    CreditLedgerEntry,
    CreditReason,
    InsufficientCreditsError,
    LedgerWrite,
    can_afford,
)


class InMemoryCreditRepository(CreditRepository):
    """Dict-backed ledger with the same atomicity guarantees within a process."""

    def __init__(self) -> None:
        self._balances: dict[str, CreditBalance] = {}
        self._entries: dict[str, list[CreditLedgerEntry]] = {}
        self._lock = asyncio.Lock()

    async def get_balance(self, user_id: str) -> CreditBalance:
        key = str(user_id)
        async with self._lock:
            return self._balances.get(key) or CreditBalance(user_id=UUID(key))

    async def list_entries(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        async with self._lock:
            entries = list(reversed(self._entries.get(str(user_id), [])))
        return entries[offset : offset + max(1, min(limit, 200))]

    async def record(
        self,
        user_id: str,
        delta: int,
        reason: CreditReason,
        reference_id: str | None = None,
        description: str | None = None,
        allow_overdraft: bool = False,
    ) -> CreditLedgerEntry:
        if delta == 0:
            raise ValueError("Ledger delta must be non-zero.")

        async with self._lock:
            return self._apply(
                str(user_id),
                LedgerWrite(delta, reason, reference_id, description, allow_overdraft),
            )

    async def record_batch(
        self, user_id: str, writes: Sequence[LedgerWrite]
    ) -> list[CreditLedgerEntry]:
        if any(w.delta == 0 for w in writes):
            raise ValueError("Ledger delta must be non-zero.")

        key = str(user_id)
        async with self._lock:
            # All or nothing: restore the account if a later write is refused.
            balance_before = self._balances.get(key)
            entries_before = list(self._entries.get(key, []))
            try:
                return [self._apply(key, w) for w in writes]
            except Exception:
                if balance_before is None:
                    self._balances.pop(key, None)
                else:
                    self._balances[key] = balance_before
                self._entries[key] = entries_before
                raise

    def _apply(self, key: str, write: LedgerWrite) -> CreditLedgerEntry:
        """Apply one write. The caller holds ``self._lock``."""
        entries = self._entries.setdefault(key, [])

        if write.reference_id is not None:
            for entry in entries:
                if entry.reference_id == write.reference_id:
                    return entry

        current = self._balances.get(key) or CreditBalance(user_id=UUID(key))
        delta = write.delta

        if delta < 0 and not write.allow_overdraft and not can_afford(current.balance, -delta):
            raise InsufficientCreditsError(required=-delta, available=current.balance)

        balance_after = current.balance + delta
        self._balances[key] = CreditBalance(
            user_id=current.user_id,
            balance=balance_after,
            lifetime_granted=current.lifetime_granted + (delta if delta > 0 else 0),
            lifetime_spent=current.lifetime_spent + (-delta if delta < 0 else 0),
            updated_at=datetime.now(UTC),
        )

        entry = CreditLedgerEntry(
            id=uuid4(),
            user_id=current.user_id,
            delta=delta,
            balance_after=balance_after,
            reason=write.reason,
            reference_id=write.reference_id,
            description=write.description,
        )
        entries.append(entry)
        return entry

    async def grant_monthly_allowance(
        self,
        user_id: str,
        credits: int,
        period_key: str,
    ) -> CreditLedgerEntry | None:
        if credits <= 0:
            return None
        reference_id = f"monthly:{period_key}"
        async with self._lock:
            for entry in self._entries.get(str(user_id), []):
                if entry.reference_id == reference_id:
                    return None
        return await self.record(
            user_id,
            delta=credits,
            reason=CreditReason.MONTHLY_GRANT,
            reference_id=reference_id,
            description=f"Monthly allowance for {period_key}",
            allow_overdraft=True,
        )
