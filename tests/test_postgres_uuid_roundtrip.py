"""asyncpg returns uuid.UUID for a UUID column, and the repos must accept it.

Every `user_id` column in migrations/ is declared `UUID` (001_saas_init.sql:19,
36, 48; 007_credits_and_api_keys.sql:15, 24, 46), and asyncpg decodes a UUID
column to a `uuid.UUID` object, not a string. Two repositories re-wrapped that
value in `UUID(...)`, which raises:

    AttributeError: 'asyncpg.pgproto.pgproto.UUID' object has no attribute 'replace'

Verified against a real PostgreSQL 16.14 container before the fix:
`PostgresQuotaRepository.get_quota` raised on every call, while
`PostgresCreditRepository.get_balance`, which never wrapped, returned fine.

That mattered more than a crash. `api/dependencies.py:659-667` catches
`Exception` from the quota check and returns `QuotaResult(allowed=True,
remaining=10)`, so on any PostgreSQL deployment the failure was swallowed into
an allow on every request, and quota was never enforced at all.

The existing mocks in tests/test_saas_quota_repo.py pass `user_id` as a *string*,
which is why this survived: `UUID(str)` succeeds, `UUID(UUID)` does not. These
tests use the type asyncpg actually returns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository


@pytest.fixture
def quota_repo():
    """Patch the CLASS attribute: _get_pool() reads _pool off the class."""
    pool = AsyncMock()
    original = PostgresQuotaRepository._pool
    PostgresQuotaRepository._pool = pool
    try:
        yield PostgresQuotaRepository("postgresql://test"), pool
    finally:
        PostgresQuotaRepository._pool = original


@pytest.fixture
def subscription_repo():
    pool = AsyncMock()
    original = PostgresSubscriptionRepository._pool
    PostgresSubscriptionRepository._pool = pool
    try:
        yield PostgresSubscriptionRepository("postgresql://test"), pool
    finally:
        PostgresSubscriptionRepository._pool = original


@pytest.mark.asyncio
async def test_get_quota_accepts_the_uuid_object_asyncpg_returns(quota_repo):
    """The proof-of-defect: this raised AttributeError before the fix."""
    repo, pool = quota_repo
    uid = uuid4()
    pool.fetchrow.return_value = {
        "user_id": uid,  # a real UUID object, as asyncpg returns
        "tier": "free",
        "used_queries": 3,
        "max_queries": 20,
        "period_start": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    quota = await repo.get_quota(str(uid))

    assert quota.user_id == uid
    assert isinstance(quota.user_id, UUID)


@pytest.mark.asyncio
async def test_get_subscription_accepts_the_uuid_object_asyncpg_returns(subscription_repo):
    repo, pool = subscription_repo
    uid = uuid4()
    pool.fetchrow.return_value = {
        "user_id": uid,
        "tier": "free",
        "status": "active",
        "stripe_sub_id": None,
        "stripe_customer_id": None,
        "paypal_sub_id": None,
        "current_period_end": datetime.now(UTC),
    }

    sub = await repo.get_subscription_by_user(str(uid))

    assert sub is not None
    assert sub.user_id == uid
    assert isinstance(sub.user_id, UUID)


@pytest.mark.asyncio
async def test_quota_period_start_may_be_null_from_a_fresh_row(quota_repo):
    """Boundary: period_start is nullable with no DEFAULT and no INSERT sets it.

    The repo must hand the None onward rather than choke on it; the guard that
    treats it as a stale period lives in QuotaService.check().
    """
    repo, pool = quota_repo
    uid = uuid4()
    pool.fetchrow.return_value = {
        "user_id": uid,
        "tier": "free",
        "used_queries": 0,
        "max_queries": 20,
        "period_start": None,
        "updated_at": datetime.now(UTC),
    }

    quota = await repo.get_quota(str(uid))

    assert quota.period_start is None
    assert quota.user_id == uid


@pytest.mark.asyncio
async def test_get_subscription_returns_none_when_absent(subscription_repo):
    """No-regression: an absent row is still None, not an exception."""
    repo, pool = subscription_repo
    pool.fetchrow.return_value = None

    assert await repo.get_subscription_by_user(str(uuid4())) is None
