"""PRV-2: a hung Valkey must not turn a paying user into FREE.

Seen locally: with no Valkey running, an Enterprise user resolved to `free`.
The cache read hung for the socket timeout (2 s), which was longer than the
1 s `TIER_LOOKUP_TIMEOUT_S`, so the database was never reached.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from reasoner.application.services import spend_limit_service as sls
from reasoner.core.constants_limits import DB_TIER_QUERY_BUDGET_S, VALKEY_OP_TIMEOUT_S
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.persistence.cached_subscription_repo import (
    CachedSubscriptionRepository,
)

pytestmark = pytest.mark.unit

USER_ID = "22222222-2222-2222-2222-222222222222"


class _HungValkey:
    async def get(self, key):
        await asyncio.sleep(5.0)

    async def setex(self, key, ttl, value):
        await asyncio.sleep(5.0)

    async def delete(self, *keys):
        await asyncio.sleep(5.0)


class _Db:
    async def get_subscription_by_user(self, user_id):
        return Subscription(
            id=uuid4(),
            user_id=UUID(USER_ID),
            tier=SubscriptionTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_1",
            stripe_customer_id="cus_1",
            current_period_end=datetime.now(UTC),
        )


def test_tier_budget_exceeds_what_the_cache_path_can_spend() -> None:
    """A read and a write may each use a full operation bound, then the DB runs."""
    assert sls.TIER_LOOKUP_TIMEOUT_S > 2 * VALKEY_OP_TIMEOUT_S + DB_TIER_QUERY_BUDGET_S


async def test_hung_cache_still_resolves_the_paid_tier(monkeypatch) -> None:
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.cached_subscription_repo.get_valkey_pool",
        lambda: _HungValkey(),
    )
    repo = CachedSubscriptionRepository(_Db())
    monkeypatch.setattr(sls, "_get_subscription_repo", lambda: repo)

    started = time.monotonic()
    tier = await sls.resolve_user_tier(USER_ID, use_fallback_cache=False)

    assert tier is SubscriptionTier.ENTERPRISE
    assert time.monotonic() - started < sls.TIER_LOOKUP_TIMEOUT_S
