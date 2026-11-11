"""Audit 6 finding 5: concurrent webhooks cannot create two rows for one subscription.

The unique indexes live in migration 20261110_000400 (checked live by
tests/integration/test_alembic_schema_contract.py). Here: the adapter takes the
UPDATE path after losing the insert race.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

pytestmark = pytest.mark.unit


def _sub() -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=uuid4(),
        tier=SubscriptionTier.PRO,
        status=SubscriptionStatus.ACTIVE,
        stripe_subscription_id="sub_1",
    )


def _repo(side_effect) -> PostgresSubscriptionRepository:
    repo = PostgresSubscriptionRepository.__new__(PostgresSubscriptionRepository)
    repo._upsert_once = AsyncMock(side_effect=side_effect)
    return repo


@pytest.mark.asyncio
async def test_lost_insert_race_retries_once_and_returns_the_second_result():
    repo = _repo([asyncpg.UniqueViolationError(), True])
    assert await repo.upsert_subscription(_sub()) is True
    assert repo._upsert_once.await_count == 2


@pytest.mark.asyncio
async def test_a_second_violation_is_not_swallowed():
    repo = _repo([asyncpg.UniqueViolationError(), asyncpg.UniqueViolationError()])
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.upsert_subscription(_sub())


@pytest.mark.asyncio
async def test_no_violation_is_a_single_pass():
    repo = _repo([False])
    assert await repo.upsert_subscription(_sub()) is False
    assert repo._upsert_once.await_count == 1
