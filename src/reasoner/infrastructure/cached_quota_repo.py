"""
Redis-backed quota repository with graceful DB fallback.

Caches quota checks in Redis to reduce PostgreSQL load.
On Redis failure, falls through to the underlying repository
so that quota enforcement never becomes a hard dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.application.ports.quota_repository import QuotaRepository
from reasoner.domain.saas import QuotaResult, UsageQuota

logger = logging.getLogger(__name__)


class CachedQuotaRepository:
    """
    Cache-aside decorator for a QuotaRepository.

    - Reads hit Redis first, falling back to the underlying repo on miss or error.
    - Writes invalidate the Redis cache so the next read is fresh.
    """

    def __init__(self, redis_client: Any, fallback_repo: QuotaRepository):
        self._redis = redis_client
        self._fallback = fallback_repo
        self._cache_ttl_seconds = 60

    def _key(self, user_id: str) -> str:
        return f"quota:{user_id}"

    async def get_quota(self, user_id: str) -> UsageQuota:
        """Fetch quota from cache or fallback repository."""
        try:
            cached = await self._redis.get(self._key(user_id))
            if cached is not None:
                # Redis returns bytes or str depending on client; handle both
                data = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                return UsageQuota.model_validate_json(data)
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("Redis quota cache unavailable, falling back to DB: %s", exc)
        except Exception as exc:
            logger.warning("Redis quota cache error, falling back to DB: %s", exc)

        quota = await self._fallback.get_quota(user_id)

        # Best-effort cache write
        try:
            await self._redis.setex(
                self._key(user_id),
                self._cache_ttl_seconds,
                quota.model_dump_json(),
            )
        except Exception:
            pass

        return quota

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        """Pass through to fallback and invalidate cache on mutation."""
        result = await self._fallback.check_and_increment(user_id, preset)
        try:
            await self._redis.delete(self._key(user_id))
        except Exception:
            pass
        return result

    async def reset_monthly(self, user_id: str) -> None:
        """Pass through to fallback and invalidate cache on mutation."""
        await self._fallback.reset_monthly(user_id)
        try:
            await self._redis.delete(self._key(user_id))
        except Exception:
            pass

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Pass through to fallback and invalidate cache on mutation."""
        await self._fallback.log_query(
            user_id, preset, method, tokens_in, tokens_out, cost_usd
        )
        try:
            await self._redis.delete(self._key(user_id))
        except Exception:
            pass
