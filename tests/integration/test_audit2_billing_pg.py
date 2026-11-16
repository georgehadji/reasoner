"""PR 3 billing rows that only a real Postgres can show: BIL-14, BIL-15, BIL-16.

Each test migrates a throwaway database with `alembic upgrade head` (the same
helpers as test_alembic_schema_contract.py) on the server behind
REASONER_TEST_PG_DSN.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.persistence.pg_pool import close_shared_pools
from tests.integration.test_alembic_schema_contract import (
    DSN,
    _alembic_upgrade,
    _fresh_database,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]

T1 = datetime(2026, 10, 1, tzinfo=UTC)
T2 = datetime(2026, 10, 2, tzinfo=UTC)


async def _user(dsn: str) -> str:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        return str(await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex}@t.local"
        ))
    finally:
        await conn.close()


def _subscription_repo(dsn: str):
    from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

    return PostgresSubscriptionRepository(dsn)


def _sub(user_id: str, sub_id: str, status=SubscriptionStatus.ACTIVE) -> Subscription:
    return Subscription(
        id=uuid4(), user_id=user_id, tier=SubscriptionTier.PRO, status=status,
        stripe_subscription_id=sub_id, stripe_customer_id="cus_1",
    )


async def test_a_retried_older_event_cannot_reactivate_a_cancelled_plan():
    """BIL-15: deleted(t=2), then a retried updated(active, t=1)."""
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        try:
            assert await repo.upsert_subscription(_sub(uid, "sub_1"), T1)
            assert await repo.set_subscription_status("sub_1", "cancelled", T2)
            assert not await repo.upsert_subscription(_sub(uid, "sub_1"), T1)
            assert not await repo.set_subscription_status("sub_1", "active", T1)
            current = await repo.get_subscription_by_user(uid)
        finally:
            await close_shared_pools()
    assert current.status is SubscriptionStatus.CANCELLED


async def test_a_second_subscription_gets_its_own_row():
    """BIL-14: the user-id fallback no longer overwrites a row tracking another sub."""
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        try:
            await repo.upsert_subscription(_sub(uid, "sub_a"), T1)
            await repo.upsert_subscription(_sub(uid, "sub_b"), T2)
        finally:
            await close_shared_pools()
        conn = await asyncpg.connect(dsn)
        try:
            ids = {r["stripe_sub_id"] for r in await conn.fetch(
                "SELECT stripe_sub_id FROM subscriptions WHERE user_id = $1", uid
            )}
        finally:
            await conn.close()
    # Both rows exist, so account deletion (which cancels every non-cancelled
    # row) reaches both subscriptions.
    assert ids == {"sub_a", "sub_b"}


async def test_racing_duplicate_references_return_one_entry():
    """BIL-16: two concurrent record() calls with one reference."""
    from reasoner.domain.credits import CreditReason
    from reasoner.infrastructure.persistence.credit_repo_postgres import PostgresCreditRepository

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = PostgresCreditRepository(dsn)
        try:
            await repo.record(uid, 1000, CreditReason.ADMIN_ADJUSTMENT)
            # Open the connections first: otherwise each call finishes while the
            # next is still connecting, and the race never happens.
            pool = await repo._get_pool()
            size = pool.get_max_size()  # the shared pool; a larger warm-up would wait forever
            warm = [await pool.acquire() for _ in range(size)]
            for conn in warm:
                await pool.release(conn)
            # One call per connection, so the calls really overlap on the pool.
            entries = await asyncio.gather(*(
                repo.record(uid, -10, CreditReason.PIPELINE_RUN, reference_id="run-1")
                for _ in range(size)
            ))
            balance = await repo.get_balance(uid)
        finally:
            await close_shared_pools()
    assert len({e.id for e in entries}) == 1
    assert balance.balance == 990
