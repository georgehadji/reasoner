"""
Postgres implementation of CreditRepository.

Every mutation runs in a single transaction with the balance row locked
(``SELECT ... FOR UPDATE``), so concurrent runs cannot both read the same
balance and spend it twice. Idempotency is enforced by the partial unique
index on ``(user_id, reference_id)``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from reasoner.core.ports.credit_repository import CreditRepository
from reasoner.domain.credits import (
    CreditBalance,
    CreditLedgerEntry,
    CreditReason,
    InsufficientCreditsError,
    LedgerWrite,
    can_afford,
)
from reasoner.infrastructure.persistence.pg_pool import get_shared_pool

logger = logging.getLogger(__name__)

_LEDGER_COLUMNS = (
    "id, user_id, delta, balance_after, reason, reference_id, description, created_at"
)
_ORPHAN_LOOKBACK = timedelta(days=7)
_SELECT_BY_REFERENCE = (
    f"SELECT {_LEDGER_COLUMNS} FROM credit_ledger WHERE user_id = $1 AND reference_id = $2"
)


def _to_entry(row: asyncpg.Record) -> CreditLedgerEntry:
    return CreditLedgerEntry(
        id=row["id"],
        user_id=row["user_id"],
        delta=row["delta"],
        balance_after=row["balance_after"],
        reason=CreditReason(row["reason"]),
        reference_id=row["reference_id"],
        description=row["description"],
        created_at=row["created_at"],
    )


class PostgresCreditRepository(CreditRepository):
    """Atomic credit ledger storage in PostgreSQL."""

    def __init__(self, dsn: str, pool_size: int | None = None):
        # pool_size is accepted for compatibility and ignored: the pool is the
        # shared per-worker one (pg_pool), sized by DB_POOL_SIZE.
        self._dsn = dsn

    async def _get_pool(self) -> asyncpg.Pool:
        return await get_shared_pool(self._dsn)

    # ── Reads ──────────────────────────────────────────────────────────

    async def get_balance(self, user_id: str) -> CreditBalance:
        uid = UUID(str(user_id))
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT user_id, balance, lifetime_granted, lifetime_spent, updated_at "
            "FROM user_credits WHERE user_id = $1",
            uid,
        )
        if row is None:
            await pool.execute(
                "INSERT INTO user_credits (user_id) VALUES ($1) "
                "ON CONFLICT (user_id) DO NOTHING",
                uid,
            )
            row = await pool.fetchrow(
                "SELECT user_id, balance, lifetime_granted, lifetime_spent, updated_at "
                "FROM user_credits WHERE user_id = $1",
                uid,
            )

        return CreditBalance(
            user_id=row["user_id"],
            balance=row["balance"],
            lifetime_granted=row["lifetime_granted"],
            lifetime_spent=row["lifetime_spent"],
            updated_at=row["updated_at"],
        )

    async def list_entries(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            f"SELECT {_LEDGER_COLUMNS} FROM credit_ledger "
            "WHERE user_id = $1 ORDER BY created_at DESC, id DESC LIMIT $2 OFFSET $3",
            UUID(str(user_id)),
            max(1, min(limit, 200)),
            max(0, offset),
        )
        return [_to_entry(r) for r in rows]

    async def list_orphaned_reservations(
        self, older_than: datetime, limit: int = 100
    ) -> list[CreditLedgerEntry]:
        pool = await self._get_pool()
        # 8 == len(":reserve"): strip it to get the run's own reference.
        rows = await pool.fetch(
            "SELECT r.id, r.user_id, r.delta, r.balance_after, r.reason, r.reference_id, "
            "r.description, r.created_at FROM credit_ledger r "
            # Lower bound keeps the partial index scan (migration 20261114_000800)
            # off ancient rows; a reserve older than this is past recovery.
            "WHERE r.reference_id LIKE '%:reserve' AND r.created_at < $1 "
            "AND r.created_at > $3 "
            "AND NOT EXISTS (SELECT 1 FROM credit_ledger s WHERE s.user_id = r.user_id "
            "AND s.reference_id IN (left(r.reference_id, -8), "
            "left(r.reference_id, -8) || ':release')) "
            "ORDER BY r.created_at LIMIT $2",
            older_than,
            max(1, min(limit, 500)),
            datetime.now(UTC) - _ORPHAN_LOOKBACK,
        )
        return [_to_entry(r) for r in rows]

    # ── Writes ─────────────────────────────────────────────────────────

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

        uid = UUID(str(user_id))
        pool = await self._get_pool()

        try:
            return await self._record_locked(
                pool, uid, delta, reason, reference_id, description, allow_overdraft
            )
        except asyncpg.UniqueViolationError:
            # Belt and braces: the lookup runs under the balance lock, so a
            # racing duplicate normally waits and finds the winner. If one still
            # collides, the winner's entry is the answer, not a 500
            # (docs/plans/audit-remediation-2-2026-10-20.md BIL-16).
            existing = await pool.fetchrow(
                _SELECT_BY_REFERENCE,
                uid,
                reference_id,
            )
            if existing is None:
                raise
            return _to_entry(existing)

    async def record_batch(
        self, user_id: str, writes: Sequence[LedgerWrite]
    ) -> list[CreditLedgerEntry]:
        if not writes:
            return []
        if any(w.delta == 0 for w in writes):
            raise ValueError("Ledger delta must be non-zero.")

        uid = UUID(str(user_id))
        pool = await self._get_pool()
        try:
            async with pool.acquire(timeout=10.0) as conn:
                async with conn.transaction():
                    balance = await self._lock_balance(conn, uid)
                    entries: list[CreditLedgerEntry] = []
                    for write in writes:
                        entry, balance = await self._apply_write(conn, uid, balance, write)
                        if entry is not None:
                            entries.append(entry)
                    return entries
        except asyncpg.UniqueViolationError:
            # A racing duplicate of one of these references won. The transaction
            # rolled back, and each write is idempotent on its own, so replay them
            # one by one: the winner's entries come back, the rest are applied.
            out: list[CreditLedgerEntry] = []
            for w in writes:
                if w.requires_reference is None:
                    out.append(await self.record(
                        user_id, w.delta, w.reason, w.reference_id, w.description,
                        w.allow_overdraft,
                    ))
                else:  # keep the precondition: a one-write batch re-checks it
                    out.extend(await self.record_batch(user_id, [w]))
            return out

    async def _record_locked(
        self, pool, uid: UUID, delta: int, reason: CreditReason,
        reference_id: str | None, description: str | None, allow_overdraft: bool,
    ) -> CreditLedgerEntry:
        async with pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                balance = await self._lock_balance(conn, uid)
                entry, _ = await self._apply_write(
                    conn, uid, balance,
                    LedgerWrite(delta, reason, reference_id, description, allow_overdraft),
                )
                if entry is None:  # record() never sets requires_reference, so this cannot skip
                    raise RuntimeError("ledger write was skipped without a precondition")
                return entry

    @staticmethod
    async def _lock_balance(conn, uid: UUID) -> int:
        """Lock (or create) the balance row and return the balance.

        The duplicate check in ``_apply_write`` then runs under that lock, so two
        calls with one reference serialise instead of both passing the check.
        """
        await conn.execute(
            "INSERT INTO user_credits (user_id) VALUES ($1) "
            "ON CONFLICT (user_id) DO NOTHING",
            uid,
        )
        row = await conn.fetchrow(
            "SELECT balance FROM user_credits WHERE user_id = $1 FOR UPDATE",
            uid,
        )
        return row["balance"]

    @staticmethod
    async def _apply_write(
        conn, uid: UUID, balance: int, write: LedgerWrite
    ) -> tuple[CreditLedgerEntry | None, int]:
        """Apply one write under the balance lock; returns (entry, new balance).

        A replayed ``reference_id`` returns the original entry and leaves the
        balance unchanged. A write whose ``requires_reference`` has no entry is
        skipped: (None, balance).
        """
        if write.reference_id is not None:
            existing = await conn.fetchrow(_SELECT_BY_REFERENCE, uid, write.reference_id)
            if existing is not None:
                return _to_entry(existing), balance
        if write.requires_reference is not None:
            if await conn.fetchrow(_SELECT_BY_REFERENCE, uid, write.requires_reference) is None:
                return None, balance

        delta = write.delta
        if delta < 0 and not write.allow_overdraft and not can_afford(balance, -delta):
            raise InsufficientCreditsError(required=-delta, available=balance)

        balance_after = balance + delta
        granted = delta if delta > 0 else 0
        spent = -delta if delta < 0 else 0

        await conn.execute(
            "UPDATE user_credits SET balance = $2, "
            "lifetime_granted = lifetime_granted + $3, "
            "lifetime_spent = lifetime_spent + $4, "
            "updated_at = NOW() WHERE user_id = $1",
            uid,
            balance_after,
            granted,
            spent,
        )

        entry = await conn.fetchrow(
            "INSERT INTO credit_ledger "
            "(user_id, delta, balance_after, reason, reference_id, description) "
            f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_LEDGER_COLUMNS}",
            uid,
            delta,
            balance_after,
            write.reason.value,
            write.reference_id,
            write.description,
        )
        return _to_entry(entry), balance_after

    async def grant_monthly_allowance(
        self,
        user_id: str,
        credits: int,
        period_key: str,
    ) -> CreditLedgerEntry | None:
        if credits <= 0:
            return None

        reference_id = f"monthly:{period_key}"
        uid = UUID(str(user_id))
        pool = await self._get_pool()

        already = await pool.fetchval(
            "SELECT 1 FROM credit_ledger WHERE user_id = $1 AND reference_id = $2",
            uid,
            reference_id,
        )
        if already:
            return None

        try:
            return await self.record(
                user_id,
                delta=credits,
                reason=CreditReason.MONTHLY_GRANT,
                reference_id=reference_id,
                description=f"Monthly allowance for {period_key}",
                allow_overdraft=True,
            )
        except asyncpg.UniqueViolationError:
            # Concurrent grant for the same period — the other one won.
            return None
