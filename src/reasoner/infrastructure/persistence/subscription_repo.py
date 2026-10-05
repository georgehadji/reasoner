"""
Postgres implementation for subscription persistence.

Handles subscription upserts and quota tier synchronization.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import asyncpg

from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier

logger = logging.getLogger(__name__)


class PostgresSubscriptionRepository:
    """Atomic subscription storage in PostgreSQL."""

    _pool: asyncpg.Pool | None = None
    # Shared pool-creation task. Callers await it through asyncio.shield, so a
    # caller that times out (the tier lookup is bounded at ~1s) abandons its wait
    # without cancelling the connect: the pool still completes in the background
    # and the next call finds it ready, instead of every request cancelling pool
    # creation and the tier staying FREE for as long as the first connect is slow.
    _pool_task: asyncio.Task | None = None

    def __init__(self, dsn: str, pool_size: int = 10):
        self._dsn = dsn
        self._pool_size = pool_size

    async def _create_pool(self) -> asyncpg.Pool:
        return await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=self._pool_size,
        )

    async def _get_pool(self) -> asyncpg.Pool:
        cls = PostgresSubscriptionRepository
        if cls._pool is not None:
            return cls._pool

        task = cls._pool_task
        loop = asyncio.get_running_loop()
        # A finished-and-failed task (or one from a dead loop) is replaced so the
        # next call retries; an in-flight one is shared.
        if task is None or task.get_loop() is not loop or (
            task.done() and (task.cancelled() or task.exception() is not None)
        ):
            task = loop.create_task(self._create_pool())
            task.add_done_callback(cls._on_pool_task_done)
            cls._pool_task = task

        pool = await asyncio.shield(task)
        cls._pool = pool
        return pool

    @staticmethod
    def _on_pool_task_done(task: asyncio.Task) -> None:
        # Runs even when every waiter timed out, so a late success still lands
        # and a late failure is logged rather than "never retrieved".
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("Subscription pool creation failed: %s", exc)
            return
        PostgresSubscriptionRepository._pool = task.result()

    async def upsert_subscription(self, sub: Subscription) -> None:
        """Idempotently update subscription in Postgres.

        Handles both Stripe and PayPal subscriptions by checking
        stripe_sub_id, paypal_sub_id, or user_id.
        """
        pool = await self._get_pool()
        # Try to find existing subscription by any known provider ID
        existing = None
        if sub.stripe_subscription_id:
            existing = await pool.fetchrow(
                "SELECT id FROM subscriptions WHERE stripe_sub_id = $1",
                sub.stripe_subscription_id,
            )
        if existing is None and sub.paypal_subscription_id:
            existing = await pool.fetchrow(
                "SELECT id FROM subscriptions WHERE paypal_sub_id = $1",
                sub.paypal_subscription_id,
            )
        if existing is None:
            existing = await pool.fetchrow(
                "SELECT id FROM subscriptions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
                str(sub.user_id),
            )

        if existing:
            await pool.execute(
                """
                UPDATE subscriptions
                SET user_id = $1,
                    tier = $2,
                    status = $3,
                    stripe_sub_id = COALESCE($4, stripe_sub_id),
                    stripe_customer_id = COALESCE($5, stripe_customer_id),
                    paypal_sub_id = COALESCE($6, paypal_sub_id),
                    current_period_end = $7,
                    updated_at = NOW()
                WHERE id = $8
                """,
                str(sub.user_id),
                sub.tier.value,
                sub.status.value,
                sub.stripe_subscription_id,
                sub.stripe_customer_id,
                sub.paypal_subscription_id,
                sub.current_period_end,
                existing["id"],
            )
        else:
            await pool.execute(
                """
                INSERT INTO subscriptions
                (user_id, tier, status, stripe_sub_id, stripe_customer_id, paypal_sub_id, current_period_end)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                str(sub.user_id),
                sub.tier.value,
                sub.status.value,
                sub.stripe_subscription_id,
                sub.stripe_customer_id,
                sub.paypal_subscription_id,
                sub.current_period_end,
            )

    async def sync_quota_for_subscription(self, sub: Subscription) -> None:
        """Sync quota limits for a subscription without resetting used_queries on update.

        Critical Enhancement 4.2: used_queries is NOT reset on every webhook.
        It is only reset when the tier changes (upgrade/downgrade).

        Uses explicit transaction + row-level lock to prevent race conditions
        when multiple Stripe webhooks arrive concurrently.
        """
        pool = await self._get_pool()
        tier_limits = {
            SubscriptionTier.FREE: 20,
            SubscriptionTier.PRO: 500,
            SubscriptionTier.ENTERPRISE: -1,
        }
        new_max = tier_limits[sub.tier]

        async with pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                # Lock the row (or nonexistent row) to serialize concurrent updates
                row = await conn.fetchrow(
                    "SELECT tier, used_queries FROM usage_quotas WHERE user_id = $1 FOR UPDATE",
                    str(sub.user_id),
                )

                if row is None:
                    # New user — create quota row
                    await conn.execute(
                        """
                        INSERT INTO usage_quotas (user_id, tier, max_queries, used_queries)
                        VALUES ($1, $2, $3, 0)
                        """,
                        str(sub.user_id),
                        sub.tier.value,
                        new_max,
                    )
                else:
                    old_tier = row["tier"]
                    if old_tier != sub.tier.value:
                        # Tier changed (upgrade/downgrade) — reset usage
                        await conn.execute(
                            """
                            UPDATE usage_quotas
                            SET tier = $2, max_queries = $3, used_queries = 0, updated_at = NOW()
                            WHERE user_id = $1
                            """,
                            str(sub.user_id),
                            sub.tier.value,
                            new_max,
                        )
                        logger.info(
                            "Quota reset for user %s due to tier change: %s -> %s",
                            sub.user_id, old_tier, sub.tier.value
                        )
                    else:
                        # Same tier — only update max_queries (e.g. plan metadata change)
                        await conn.execute(
                            """
                            UPDATE usage_quotas
                            SET tier = $2, max_queries = $3, updated_at = NOW()
                            WHERE user_id = $1
                            """,
                            str(sub.user_id),
                            sub.tier.value,
                            new_max,
                        )

    async def set_subscription_status(self, stripe_sub_id: str, status: str) -> None:
        """Update subscription status (e.g. past_due, cancelled)."""
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE subscriptions SET status = $1, updated_at = NOW() WHERE stripe_sub_id = $2",
            status,
            stripe_sub_id,
        )

    async def set_subscription_status_by_paypal(self, paypal_sub_id: str, status: str) -> None:
        """Update subscription status by PayPal subscription ID."""
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE subscriptions SET status = $1, updated_at = NOW() WHERE paypal_sub_id = $2",
            status,
            paypal_sub_id,
        )

    async def get_subscription_by_user(self, user_id: str) -> Subscription | None:
        """Fetch the active subscription for a user."""
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT user_id, tier, status, stripe_sub_id, stripe_customer_id, paypal_sub_id, current_period_end "
            "FROM subscriptions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            user_id,
        )
        if row is None:
            return None
        return Subscription(
            id=uuid4(),  # ephemeral id for domain object
            # asyncpg returns a uuid.UUID for a UUID column; re-wrapping raises.
            user_id=row["user_id"],
            tier=SubscriptionTier(row["tier"]),
            status=SubscriptionStatus(row["status"]),
            stripe_subscription_id=row["stripe_sub_id"],
            stripe_customer_id=row["stripe_customer_id"],
            paypal_subscription_id=row["paypal_sub_id"],
            current_period_end=row["current_period_end"],
        )
