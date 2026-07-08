"""
Postgres implementation of BillingDeadLetterPort.

Stores failed webhook events durably so they can be replayed and alerted on.
Uses the same asyncpg pool pattern as the webhook idempotency store.
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone

from reasoner.application.ports.billing_deadletter_port import (
    BillingDeadLetterPort,
    FailedWebhookEvent,
)

logger = logging.getLogger(__name__)


class PostgresBillingDeadLetterRepo(BillingDeadLetterPort):
    """Postgres-backed dead-letter store for failed webhook events.

    Uses a dedicated table `failed_webhook_events` that is NOT referenced
    by any FK from `users` — survives user deletion and provides GDPR
    accountability (deletion audit trail).
    """

    def __init__(self, pool):
        """Initialize with an existing asyncpg connection pool.

        Args:
            pool: An asyncpg pool obtained from _get_webhook_pool()
                  or created via asyncpg.create_pool().
        """
        self._pool = pool

    async def _ensure_table(self) -> None:
        """Create the failed_webhook_events table if it doesn't exist."""
        async with self._pool.acquire(timeout=10.0) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS failed_webhook_events (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    error TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    replayed_at TIMESTAMPTZ
                )
            """)

            # Index for listing failures by provider and replay status
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_provider
                ON failed_webhook_events (provider, created_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_unreplayed
                ON failed_webhook_events (created_at DESC)
                WHERE replayed_at IS NULL
            """)

    async def record_failure(
        self,
        provider: str,
        event_type: str,
        payload: dict,
        error: str,
    ) -> str:
        """Durably record a webhook processing failure."""
        await self._ensure_table()
        failure_id = str(uuid.uuid4())
        async with self._pool.acquire(timeout=10.0) as conn:
            await conn.execute(
                """
                INSERT INTO failed_webhook_events (id, provider, event_type, payload, error)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                """,
                failure_id,
                provider,
                event_type,
                json.dumps(payload),
                error,
            )
        logger.info(
            "Recorded webhook failure %s: provider=%s event_type=%s error=%s",
            failure_id, provider, event_type, error,
        )
        return failure_id

    async def list_failures(
        self,
        provider: str | None = None,
        unreplayed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FailedWebhookEvent]:
        """List recorded failures with optional filtering."""
        await self._ensure_table()

        conditions = []
        params: list = []
        param_idx = 0

        if provider:
            param_idx += 1
            conditions.append(f"provider = ${param_idx}")
            params.append(provider)
        if unreplayed_only:
            conditions.append("replayed_at IS NULL")

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT id, provider, event_type, payload, error, created_at, replayed_at
            FROM failed_webhook_events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
        """
        params.extend([limit, offset])

        async with self._pool.acquire(timeout=10.0) as conn:
            rows = await conn.fetch(query, *params)

        return [
            FailedWebhookEvent(
                id=str(row["id"]),
                provider=row["provider"],
                event_type=row["event_type"],
                payload=dict(row["payload"]),
                error=row["error"],
                created_at=row["created_at"],
                replayed_at=row["replayed_at"],
            )
            for row in rows
        ]

    async def mark_replayed(self, failure_id: str) -> bool:
        """Mark a recorded failure as successfully replayed."""
        await self._ensure_table()
        async with self._pool.acquire(timeout=10.0) as conn:
            result = await conn.execute(
                """
                UPDATE failed_webhook_events
                SET replayed_at = NOW()
                WHERE id = $1::uuid AND replayed_at IS NULL
                """,
                failure_id,
            )
            # asyncpg returns "UPDATE N" where N is rows matched
            return "UPDATE 1" in result

    async def count_unreplayed(self) -> int:
        """Return the count of failures that haven't been replayed."""
        await self._ensure_table()
        async with self._pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchval(
                "SELECT COUNT(*) FROM failed_webhook_events WHERE replayed_at IS NULL"
            )
            return row or 0
