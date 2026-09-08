"""Quota reads must survive Redis being down, and must say so when it is.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

This file used to exercise ``reasoner.infrastructure.cached_quota_repo``, a
second ``CachedQuotaRepository`` that nothing in ``src/`` imported. Its cache
had never worked: it called ``UsageQuota.model_dump_json()`` on what is a
``@dataclass(frozen=True)``, so every write raised ``AttributeError`` into an
``except Exception: pass`` and nothing was ever stored. It was deleted; this
test now covers the class that ``api/dependencies.py`` actually wires.

``test_saas_cached_quota.py`` covers hit, miss and invalidation. The gap it
leaves is the failure path, which is the one that matters operationally: the
module's docstring promises quota enforcement never becomes a hard dependency
on Redis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from reasoner.domain.saas import SubscriptionTier, UsageQuota
from reasoner.infrastructure.persistence.cached_quota_repo import CachedQuotaRepository


@pytest.mark.asyncio
async def test_redis_down_falls_back_to_db(caplog):
    """A dead Redis degrades to the DB, and leaves a WARNING behind."""
    fake_redis = AsyncMock()
    fake_redis.get.side_effect = ConnectionError("redis is down")

    now = datetime.now(UTC)
    expected_quota = UsageQuota(
        user_id="11111111-1111-1111-1111-111111111111",
        tier=SubscriptionTier.PRO,
        used_queries=42,
        max_queries=1000,
        period_start=now,
        updated_at=now,
    )
    fallback = AsyncMock()
    fallback.get_quota = AsyncMock(return_value=expected_quota)

    repo = CachedQuotaRepository(fallback)
    repo._redis = fake_redis

    with caplog.at_level(logging.WARNING):
        quota = await repo.get_quota("user-1")

    assert quota.used_queries == 42
    fallback.get_quota.assert_awaited_once_with("user-1")
    assert any("falling back to DB" in r.message for r in caplog.records), (
        f"the Redis failure was not reported, got: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_failed_invalidation_is_not_silent(caplog):
    """A delete that does not land leaves a stale quota readable for the TTL."""
    fake_redis = AsyncMock()
    fake_redis.delete.side_effect = ConnectionError("redis is down")

    fallback = AsyncMock()
    repo = CachedQuotaRepository(fallback)
    repo._redis = fake_redis

    with caplog.at_level(logging.WARNING):
        await repo.reset_monthly("user-1")

    fallback.reset_monthly.assert_awaited_once_with("user-1")
    assert any("invalidate failed" in r.message for r in caplog.records), (
        f"the failed invalidation was not reported, got: {[r.message for r in caplog.records]}"
    )
