"""Audit 9 billing SQL against a real Postgres (REASONER_TEST_PG_DSN)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from reasoner.application.services.billing_service import BillingService, _paypal_cancel
from reasoner.domain.saas import SubscriptionStatus
from tests.integration.test_alembic_schema_contract import (
    DSN,
    _alembic_upgrade,
    _fresh_database,
)
from tests.integration.test_audit2_billing_pg import T1, T2, _sub, _subscription_repo, _user

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]


def _pp(uid: str, sub_id: str, status=SubscriptionStatus.ACTIVE):
    return replace(
        _sub(uid, "x", status), stripe_subscription_id=None, paypal_subscription_id=sub_id
    )


async def test_paypal_cancel_before_activate_stays_cancelled():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        try:
            await _paypal_cancel(_pp(uid, "I-1", SubscriptionStatus.CANCELLED), repo, T2)
            assert not await repo.upsert_subscription(_pp(uid, "I-1"), T1)  # older ACTIVATED
            current = await repo.get_subscription_by_user(uid)
        finally:
            await repo.close()
    assert current.status is SubscriptionStatus.CANCELLED


async def test_get_subscription_prefers_live_row():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        try:
            await repo.upsert_subscription(_sub(uid, "sub_a"), T1)
            await repo.upsert_subscription(_sub(uid, "sub_b"), T2)
            await repo.set_subscription_status("sub_b", "cancelled", T2)
            current = await repo.get_subscription_by_user(uid)
        finally:
            await repo.close()
    assert current.stripe_subscription_id == "sub_a"


async def test_concurrent_checkouts_store_one_live_subscription():
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        port = AsyncMock()
        try:
            svc = BillingService(port)
            await asyncio.gather(*(
                svc._apply_webhook("checkout.session.completed", _sub(uid, f"sub_{i}"), repo, T1)
                for i in range(4)
            ))
        finally:
            await repo.close()
        conn = await asyncpg.connect(dsn)
        try:
            live = await conn.fetchval(
                "SELECT count(*) FROM subscriptions WHERE user_id = $1 AND status = 'active'", uid
            )
        finally:
            await conn.close()
    assert live == 1
    assert port.cancel_subscription.await_count == 3


async def test_reset_monthly_is_utc_month_start_conditional_and_keeps_tier_usage():
    import asyncpg

    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        # Session timezone far from UTC: the old SQL wrote a tz-less value into timestamptz.
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "DO $$ BEGIN EXECUTE format('ALTER DATABASE %I SET timezone = ''Asia/Tokyo''', "
                "current_database()); END $$"
            )
        finally:
            await conn.close()
        PostgresQuotaRepository._pool = None
        quota = PostgresQuotaRepository(dsn, pool_size=2)
        sub_repo = _subscription_repo(dsn)
        try:
            await sub_repo.sync_quota_for_subscription(
                _sub(uid, "s1", SubscriptionStatus.CANCELLED))
            pool = await quota._get_pool()
            await pool.execute("UPDATE usage_quotas SET used_queries = 5 WHERE user_id = $1", uid)
            # tier change (free -> pro) must keep used_queries
            await sub_repo.upsert_subscription(_sub(uid, "s1"), T1)
            await sub_repo.sync_quota_for_subscription(_sub(uid, "s1"))
            assert await pool.fetchval(
                "SELECT used_queries FROM usage_quotas WHERE user_id = $1", uid) == 5
            await quota.reset_monthly(uid)
            first = await pool.fetchrow(
                "SELECT used_queries, period_start FROM usage_quotas WHERE user_id = $1", uid)
            now = datetime.now(UTC)
            assert first["used_queries"] == 0
            assert first["period_start"] == datetime(now.year, now.month, 1, tzinfo=UTC)
            # a slot claimed after the reset survives a second (racing) reset
            await pool.execute("UPDATE usage_quotas SET used_queries = 1 WHERE user_id = $1", uid)
            await quota.reset_monthly(uid)
            assert await pool.fetchval(
                "SELECT used_queries FROM usage_quotas WHERE user_id = $1", uid) == 1
        finally:
            await sub_repo.close()
            if PostgresQuotaRepository._pool is not None:
                await PostgresQuotaRepository._pool.close()
            PostgresQuotaRepository._pool = None


async def test_release_after_the_month_reset_does_not_take_from_the_new_month():
    from datetime import timedelta

    import asyncpg

    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = PostgresQuotaRepository(dsn, pool_size=2)
        conn = await asyncpg.connect(dsn)
        try:
            await repo.get_quota(uid)  # creates the free row
            await repo.check_and_increment(uid, "p")  # the run claims in "last month"
            claimed_at = datetime.now(UTC)
            await repo.reset_monthly(uid)  # month rolls over: count 0, period_start = this month
            await repo.check_and_increment(uid, "p")  # a new-month run holds the one slot
            await conn.execute(
                "UPDATE usage_quotas SET period_start = $2 WHERE user_id = $1",
                uid, claimed_at + timedelta(days=1),  # the reset happened after the claim
            )
            await repo.release_slot(uid, claimed_at)  # the old run gives back: a no-op
            q = "SELECT used_queries FROM usage_quotas WHERE user_id = $1"
            kept = await conn.fetchval(q, uid)
            await repo.release_slot(uid)  # unguarded call still releases
            freed = await conn.fetchval(q, uid)
        finally:
            await conn.close()
            if PostgresQuotaRepository._pool is not None:
                await PostgresQuotaRepository._pool.close()
                PostgresQuotaRepository._pool = None
    assert (kept, freed) == (1, 0)
