"""
Cache-aside decorator for QuotaRepository.

Redis caches hot quota reads (TTL 60s).
Writes invalidate the cache immediately.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from reasoner.domain.saas import UsageQuota, QuotaResult
from reasoner.application.ports.quota_repository import QuotaRepository
from reasoner.infrastructure.valkey.client import get_valkey_pool

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 60


class CachedQuotaRepository(QuotaRepository):
    """Wraps a QuotaRepository with Redis cache-aside."""

    def __init__(self, underlying: QuotaRepository):
        self._underlying = underlying
        self._redis = get_valkey_pool()

    def _cache_key(self, user_id: str) -> str:
        return f"quota:{user_id}"

    async def get_quota(self, user_id: str) -> UsageQuota:
        cache_key = self._cache_key(user_id)
        try:
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return UsageQuota(
                    user_id=UUID(data["user_id"]),
                    tier=data["tier"],
                    used_queries=data["used_queries"],
                    max_queries=data["max_queries"],
                    period_start=datetime.fromisoformat(data["period_start"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                )
        except Exception as exc:
            logger.warning("Redis quota cache read failed, falling back to DB: %s", exc)

        quota = await self._underlying.get_quota(user_id)
        try:
            await self._redis.setex(
                cache_key,
                CACHE_TTL_SECONDS,
                json.dumps({
                    "user_id": str(quota.user_id),
                    "tier": quota.tier.value,
                    "used_queries": quota.used_queries,
                    "max_queries": quota.max_queries,
                    "period_start": quota.period_start.isoformat(),
                    "updated_at": quota.updated_at.isoformat(),
                }),
            )
        except Exception as exc:
            logger.warning("Redis quota cache write failed: %s", exc)
        return quota

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        result = await self._underlying.check_and_increment(user_id, preset)
        try:
            await self._redis.delete(self._cache_key(user_id))
        except Exception as exc:
            logger.warning("Redis quota cache invalidate failed: %s", exc)
        return result

    async def reset_monthly(self, user_id: str) -> None:
        await self._underlying.reset_monthly(user_id)
        try:
            await self._redis.delete(self._cache_key(user_id))
        except Exception as exc:
            logger.warning("Redis quota cache invalidate failed: %s", exc)

    async def log_query(self, user_id: str, preset: str, method: str, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        await self._underlying.log_query(user_id, preset, method, tokens_in, tokens_out, cost_usd)
        try:
            await self._redis.delete(self._cache_key(user_id))
        except Exception as exc:
            logger.warning("Redis quota cache invalidate failed: %s", exc)
