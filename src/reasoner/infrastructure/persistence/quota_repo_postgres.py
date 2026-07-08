"""
Postgres implementation of QuotaRepository.

Uses asyncpg with parameterized queries.
All write operations are transactional to prevent race conditions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from reasoner.domain.saas import UsageQuota, QuotaResult, SubscriptionTier
from reasoner.application.ports.quota_repository import QuotaRepository

logger = logging.getLogger(__name__)


class PostgresQuotaRepository(QuotaRepository):
    """Atomic quota storage in PostgreSQL."""

    _pool: asyncpg.Pool | None = None
    _pool_lock: asyncio.Lock | None = None

    def __init__(self, dsn: str, pool_size: int | None = None):
        self._dsn = dsn
        self._pool_size = pool_size if pool_size is not None else int(
            os.environ.get("DB_POOL_SIZE", "10")
        )

    async def _get_pool(self) -> asyncpg.Pool:
        if PostgresQuotaRepository._pool_lock is None:
            PostgresQuotaRepository._pool_lock = asyncio.Lock()

        if PostgresQuotaRepository._pool is not None:
            return PostgresQuotaRepository._pool
            
        async with PostgresQuotaRepository._pool_lock:
            if PostgresQuotaRepository._pool is None:
                PostgresQuotaRepository._pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=1,
                    max_size=self._pool_size,
                )
            return PostgresQuotaRepository._pool

    async def get_quota(self, user_id: str) -> UsageQuota:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT user_id, tier, used_queries, max_queries, period_start, updated_at "
            "FROM usage_quotas WHERE user_id = $1",
            user_id,
        )
        if row is None:
            # User has no quota row yet — create with free defaults
            await pool.execute(
                "INSERT INTO usage_quotas (user_id, tier, max_queries) VALUES ($1, $2, $3) "
                "ON CONFLICT (user_id) DO NOTHING",
                user_id, SubscriptionTier.FREE.value, 20,
            )
            row = await pool.fetchrow(
                "SELECT user_id, tier, used_queries, max_queries, period_start, updated_at "
                "FROM usage_quotas WHERE user_id = $1",
                user_id,
            )

        return UsageQuota(
            user_id=UUID(row["user_id"]),
            tier=SubscriptionTier(row["tier"]),
            used_queries=row["used_queries"],
            max_queries=row["max_queries"],
            period_start=row["period_start"],
            updated_at=row["updated_at"],
        )

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Lock row and read current state
                row = await conn.fetchrow(
                    "SELECT tier, used_queries, max_queries FROM usage_quotas "
                    "WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )

                if row is None:
                    # Create default quota row
                    await conn.execute(
                        "INSERT INTO usage_quotas (user_id, tier, max_queries) VALUES ($1, $2, $3)",
                        user_id, SubscriptionTier.FREE.value, 20,
                    )
                    row = {"tier": SubscriptionTier.FREE.value, "used_queries": 0, "max_queries": 20}

                tier = SubscriptionTier(row["tier"])
                used = row["used_queries"]
                max_q = row["max_queries"]

                if max_q == -1:
                    return QuotaResult(allowed=True, remaining=-1)

                remaining = max(0, max_q - used)
                if remaining <= 0:
                    return QuotaResult(
                        allowed=False,
                        remaining=0,
                        reason=f"Quota exceeded: {used}/{max_q} queries used.",
                    )

                # Increment atomically
                await conn.execute(
                    "UPDATE usage_quotas SET used_queries = used_queries + 1, updated_at = (NOW() AT TIME ZONE 'UTC') "
                    "WHERE user_id = $1",
                    user_id,
                )

                return QuotaResult(allowed=True, remaining=remaining - 1)

    async def reset_monthly(self, user_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE usage_quotas SET used_queries = 0, period_start = date_trunc('month', (NOW() AT TIME ZONE 'UTC')), "
            "updated_at = (NOW() AT TIME ZONE 'UTC') WHERE user_id = $1",
            user_id,
        )

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO query_log (user_id, preset, method, tokens_in, tokens_out, cost_usd) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            user_id, preset, method, tokens_in, tokens_out, cost_usd,
        )
