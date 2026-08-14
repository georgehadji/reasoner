"""
Postgres implementation of CreditRepository.

Every mutation runs in a single transaction with the balance row locked
(``SELECT ... FOR UPDATE``), so concurrent runs cannot both read the same
balance and spend it twice. Idempotency is enforced by the partial unique
index on ``(user_id, reference_id)``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg

from reasoner.core.ports.credit_repository import CreditRepository
from reasoner.domain.credits import (
    CreditBalance,
    CreditLedgerEntry,
    CreditReason,
    InsufficientCreditsError,
    can_afford,
)

logger = logging.getLogger(__name__)

_LEDGER_COLUMNS = (
    "id, user_id, delta, balance_after, reason, reference_id, description, created_at"
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

    _pool: asyncpg.Pool | None = None
    _pool_lock: asyncio.Lock | None = None

    def __init__(self, dsn: str, pool_size: int | None = None):
        self._dsn = dsn
        self._pool_size = (
            pool_size
            if pool_size is not None
            else int(os.environ.get("DB_POOL_SIZE", "10"))
        )

    async def _get_pool(self) -> asyncpg.Pool:
        if PostgresCreditRepository._pool_lock is None:
            PostgresCreditRepository._pool_lock = asyncio.Lock()

        if PostgresCreditRepository._pool is not None:
            return PostgresCreditRepository._pool

        async with PostgresCreditRepository._pool_lock:
            if PostgresCreditRepository._pool is None:
                PostgresCreditRepository._pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=1,
                    max_size=self._pool_size,
                )
            return PostgresCreditRepository._pool

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

    # ── Writes ─────────────────────────────────────────────────────────

    async def record(
        self,
        user_id: str,
        delta: int,
        reason: CreditReason,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        allow_overdraft: bool = False,
    ) -> CreditLedgerEntry:
        if delta == 0:
            raise ValueError("Ledger delta must be non-zero.")

        uid = UUID(str(user_id))
        pool = await self._get_pool()

        async with pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                if reference_id is not None:
                    existing = await conn.fetchrow(
                        f"SELECT {_LEDGER_COLUMNS} FROM credit_ledger "
                        "WHERE user_id = $1 AND reference_id = $2",
                        uid,
                        reference_id,
                    )
                    if existing is not None:
                        return _to_entry(existing)

                # Lock (or create) the balance row before reading it.
                await conn.execute(
                    "INSERT INTO user_credits (user_id) VALUES ($1) "
                    "ON CONFLICT (user_id) DO NOTHING",
                    uid,
                )
                row = await conn.fetchrow(
                    "SELECT balance FROM user_credits WHERE user_id = $1 FOR UPDATE",
                    uid,
                )
                balance = row["balance"]

                if delta < 0 and not allow_overdraft and not can_afford(balance, -delta):
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

                try:
                    entry = await conn.fetchrow(
                        "INSERT INTO credit_ledger "
                        "(user_id, delta, balance_after, reason, reference_id, description) "
                        f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_LEDGER_COLUMNS}",
                        uid,
                        delta,
                        balance_after,
                        reason.value,
                        reference_id,
                        description,
                    )
                except asyncpg.UniqueViolationError:
                    # Another transaction inserted the same reference between our
                    # lookup and insert. Their entry is authoritative.
                    raise

                return _to_entry(entry)

    async def grant_monthly_allowance(
        self,
        user_id: str,
        credits: int,
        period_key: str,
    ) -> Optional[CreditLedgerEntry]:
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
