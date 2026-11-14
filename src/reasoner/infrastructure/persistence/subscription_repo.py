"""
Postgres implementation for subscription persistence.

Handles subscription upserts and quota tier synchronization.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import asyncpg

from reasoner.core.state_machine import Machine
from reasoner.domain.saas import (
    SUBSCRIPTION_TRANSITIONS,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
)
from reasoner.infrastructure.persistence.pg_pool import advisory_lock, get_shared_pool

logger = logging.getLogger(__name__)

# Every write below applies unless the row already holds a newer event
# (BIL-15): "event time is NULL (unknown) OR no event yet OR last <= event".
# The SQL is spelled out literally in each statement rather than composed.
#
# The same writes also obey SUBSCRIPTION_MACHINE (SM-M1): a cancelled row cannot
# be revived, even by an event with an equal timestamp. The guard passes a stored
# status the machine does not know (legacy data), so it never blocks old rows.
_KNOWN_STATUSES = [s.value for s in SubscriptionStatus]
SUBSCRIPTION_MACHINE = Machine(
    "subscription", SUBSCRIPTION_TRANSITIONS, initial=SubscriptionStatus.ACTIVE, enforce=True
)


def statuses_that_may_become(target: str) -> list[str]:
    """Stored statuses a row may hold when it moves to ``target``: the SQL guard's input.

    An unknown ``target`` allows every known status, and the guard lets an
    unknown stored value through, so data already stored never blocks a write.
    """
    try:
        dst = SubscriptionStatus(target)
    except ValueError:
        return list(_KNOWN_STATUSES)
    # A repeated status (a re-delivered cancel) is a no-op, not a move.
    return [s.value for s in SubscriptionStatus if s == dst or SUBSCRIPTION_MACHINE.can(s, dst)]

_SET_STATUS_SQL = {
    "stripe_sub_id": (
        "UPDATE subscriptions SET status = $1, last_event_at = COALESCE($3, last_event_at), "
        "updated_at = NOW() WHERE stripe_sub_id = $2 AND ($3::timestamptz IS NULL "
        "OR last_event_at IS NULL OR last_event_at <= $3::timestamptz) "
        "AND (status = ANY($4::text[]) OR NOT status = ANY($5::text[]))"
    ),
    "paypal_sub_id": (
        "UPDATE subscriptions SET status = $1, last_event_at = COALESCE($3, last_event_at), "
        "updated_at = NOW() WHERE paypal_sub_id = $2 AND ($3::timestamptz IS NULL "
        "OR last_event_at IS NULL OR last_event_at <= $3::timestamptz) "
        "AND (status = ANY($4::text[]) OR NOT status = ANY($5::text[]))"
    ),
}


class PostgresSubscriptionRepository:
    """Atomic subscription storage in PostgreSQL."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    async def _get_pool(self) -> asyncpg.Pool:
        return await get_shared_pool(self._dsn)

    async def upsert_subscription(
        self, sub: Subscription, event_at: datetime | None = None
    ) -> bool:
        """Idempotently write a subscription. Returns False for a stale event.

        The unique indexes on the provider ids (migration 20261110_000400) make a
        concurrent insert of the same subscription fail with a unique violation.
        The row exists by then, so a second pass takes the UPDATE path and the
        BIL-15 ordering guard decides whether it applies.
        """
        try:
            return await self._upsert_once(sub, event_at)
        except asyncpg.UniqueViolationError:
            return await self._upsert_once(sub, event_at)

    async def _upsert_once(
        self, sub: Subscription, event_at: datetime | None = None
    ) -> bool:
        """One select-then-write pass. Returns False for a stale event.

        A row is matched by its provider id. The user-id fallback adopts the
        user's latest row only when that row has no id for the incoming
        provider: overwriting a row that already tracks another subscription
        lost it, so account deletion could no longer cancel it (BIL-14).

        ``event_at`` is the provider event's own time. A write older than the
        row's ``last_event_at`` is skipped, so a retried event cannot undo a
        newer one (BIL-15).
        """
        pool = await self._get_pool()
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
            latest = await pool.fetchrow(
                "SELECT id, stripe_sub_id, paypal_sub_id, status FROM subscriptions "
                "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
                str(sub.user_id),
            )
            tracks_other = latest is not None and (
                (sub.stripe_subscription_id and latest["stripe_sub_id"])
                or (sub.paypal_subscription_id and latest["paypal_sub_id"])
            )
            # A cancelled row is terminal (SM-M1): adopting a PayPal cancel
            # tombstone would rewrite it live and stop it guarding its id.
            cancelled = latest is not None and latest["status"] == "cancelled"
            existing = None if tracks_other or cancelled else latest

        if existing:
            result = await pool.execute(
                """
                UPDATE subscriptions
                SET user_id = $1,
                    tier = $2,
                    status = $3,
                    stripe_sub_id = COALESCE($4, stripe_sub_id),
                    stripe_customer_id = COALESCE($5, stripe_customer_id),
                    paypal_sub_id = COALESCE($6, paypal_sub_id),
                    current_period_end = $7,
                    last_event_at = COALESCE($9, last_event_at),
                    updated_at = NOW()
                WHERE id = $8 AND ($9::timestamptz IS NULL OR last_event_at IS NULL
                                   OR last_event_at <= $9::timestamptz)
                  AND (status = ANY($10::text[]) OR NOT status = ANY($11::text[]))
                """,
                str(sub.user_id),
                sub.tier.value,
                sub.status.value,
                sub.stripe_subscription_id,
                sub.stripe_customer_id,
                sub.paypal_subscription_id,
                sub.current_period_end,
                existing["id"],
                event_at,
                statuses_that_may_become(sub.status.value),
                _KNOWN_STATUSES,
            )
            return bool(result.endswith(" 1"))
        await pool.execute(
            """
            INSERT INTO subscriptions
            (user_id, tier, status, stripe_sub_id, stripe_customer_id, paypal_sub_id,
             current_period_end, last_event_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            str(sub.user_id),
            sub.tier.value,
            sub.status.value,
            sub.stripe_subscription_id,
            sub.stripe_customer_id,
            sub.paypal_subscription_id,
            sub.current_period_end,
            event_at,
        )
        return True

    async def record_paypal_cancel_tombstone(
        self, sub: Subscription, event_at: datetime | None
    ) -> None:
        """A cancel arrived before its ACTIVATED: store a cancelled row for it.

        Its ``last_event_at`` makes the later, older ACTIVATED lose the ordering
        guard in ``_upsert_once``. No-op when a row for the id exists (the
        status update already decided) or the user is unknown.
        """
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO subscriptions (user_id, tier, status, paypal_sub_id, "
            "current_period_end, last_event_at) "
            "SELECT $1::uuid, $2, 'cancelled', $3, $4, $5 "
            "WHERE EXISTS (SELECT 1 FROM users WHERE id = $1::uuid) "
            "AND NOT EXISTS (SELECT 1 FROM subscriptions WHERE paypal_sub_id = $3)",
            str(sub.user_id),
            sub.tier.value,
            sub.paypal_subscription_id,
            sub.current_period_end,
            event_at,
        )

    @asynccontextmanager
    async def user_lock(self, user_id: str):
        """Serialize a read-then-write on one user across workers.

        Holds a session advisory lock on one pooled connection (see
        ``pg_pool.advisory_lock``), released before the connection returns.
        """
        async with advisory_lock(self._dsn, user_id):
            yield

    async def get_user_by_stripe_sub_id(self, stripe_sub_id: str) -> str | None:
        """The user a Stripe subscription belongs to, from our own table (BIL-13)."""
        pool = await self._get_pool()
        user_id = await pool.fetchval(
            "SELECT user_id FROM subscriptions WHERE stripe_sub_id = $1", stripe_sub_id
        )
        return str(user_id) if user_id else None

    async def get_user_by_paypal_sub_id(self, paypal_sub_id: str) -> str | None:
        pool = await self._get_pool()
        user_id = await pool.fetchval(
            "SELECT user_id FROM subscriptions WHERE paypal_sub_id = $1", paypal_sub_id
        )
        return str(user_id) if user_id else None

    async def sync_quota_for_subscription(self, sub: Subscription) -> None:
        """Sync quota limits for a subscription without resetting used_queries on update.

        Critical Enhancement 4.2: used_queries is NOT reset on every webhook.
        It is never reset here; a tier change only moves the limits.

        Uses explicit transaction + row-level lock to prevent race conditions
        when multiple Stripe webhooks arrive concurrently.
        """
        pool = await self._get_pool()
        tier_limits = {
            SubscriptionTier.FREE: 20,
            SubscriptionTier.PRO: 500,
            SubscriptionTier.ENTERPRISE: -1,
        }
        # One quota row per user: it follows the user's latest live subscription,
        # not the event's. A late cancel of an old subscription must not write
        # FREE over a plan the user still pays for.
        live_tier = await pool.fetchval(
            "SELECT tier FROM subscriptions WHERE user_id = $1 "
            "AND status IN ('active', 'trialing', 'past_due') "
            "ORDER BY created_at DESC LIMIT 1",
            str(sub.user_id),
        )
        sub = replace(sub, tier=SubscriptionTier(live_tier) if live_tier else SubscriptionTier.FREE)
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
                    # Limits move, usage does not (or a cancel would hand out a fresh
                    # free allowance); the monthly reset owns the period. A same-tier
                    # event still rewrites max_queries (plan metadata change).
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
                    if row["tier"] != sub.tier.value:
                        logger.info(
                            "Quota tier changed for user %s: %s -> %s",
                            sub.user_id, row["tier"], sub.tier.value
                        )

    async def set_subscription_status(
        self, stripe_sub_id: str, status: str, event_at: datetime | None = None
    ) -> bool:
        """Update subscription status (e.g. past_due, cancelled). False if stale."""
        return await self._set_status("stripe_sub_id", stripe_sub_id, status, event_at)

    async def set_subscription_status_by_paypal(
        self, paypal_sub_id: str, status: str, event_at: datetime | None = None
    ) -> bool:
        """Update subscription status by PayPal subscription ID. False if stale."""
        return await self._set_status("paypal_sub_id", paypal_sub_id, status, event_at)

    async def reactivate_past_due_by_paypal(
        self, paypal_sub_id: str, event_at: datetime | None = None
    ) -> Subscription | None:
        """Flip a past_due PayPal subscription back to active; None if not past_due or stale."""
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "UPDATE subscriptions SET status = 'active', "
            "last_event_at = COALESCE($2, last_event_at), updated_at = NOW() "
            "WHERE paypal_sub_id = $1 AND status = 'past_due' AND ($2::timestamptz IS NULL "
            "OR last_event_at IS NULL OR last_event_at <= $2::timestamptz) "
            "RETURNING user_id, tier, paypal_sub_id, current_period_end",
            paypal_sub_id,
            event_at,
        )
        if row is None:
            return None
        return Subscription(
            id=uuid4(),
            user_id=row["user_id"],
            tier=SubscriptionTier(row["tier"]),
            status=SubscriptionStatus.ACTIVE,
            paypal_subscription_id=row["paypal_sub_id"],
            current_period_end=row["current_period_end"],
        )

    async def _set_status(
        self, column: str, sub_id: str, status: str, event_at: datetime | None
    ) -> bool:
        pool = await self._get_pool()
        result = await pool.execute(
            _SET_STATUS_SQL[column],
            status,
            sub_id,
            event_at,
            statuses_that_may_become(status),
            _KNOWN_STATUSES,
        )
        return not result.endswith(" 0")

    async def get_subscription_by_user(self, user_id: str) -> Subscription | None:
        """The user's live subscription, else their newest row."""
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT user_id, tier, status, stripe_sub_id, stripe_customer_id, paypal_sub_id, current_period_end "
            "FROM subscriptions WHERE user_id = $1 "
            "ORDER BY (status IN ('active', 'trialing', 'past_due')) DESC, created_at DESC LIMIT 1",
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
