"""
Cache-aside decorator for subscription tier lookups.

Redis caches the subscription read that gates every quota check (TTL 60s).
Subscriptions only change via Stripe/PayPal webhooks, so the billing service
invalidates the entry directly and upgrades take effect immediately rather
than after the TTL expires.

Fail-safe contract: this layer never invents a subscription. Any cache
problem degrades to the underlying repository, and any underlying error
propagates to the caller, which is responsible for falling back to FREE.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.redis.client import get_redis

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

# Cached when a user has no subscription row at all — the common free-tier
# path, and the one most worth keeping off the database.
_NO_SUBSCRIPTION = "null"


def _cache_key(user_id: str) -> str:
    return f"subscription:{user_id}"


def _serialize(sub: Subscription | None) -> str:
    if sub is None:
        return _NO_SUBSCRIPTION
    return json.dumps({
        "id": str(sub.id),
        "user_id": str(sub.user_id),
        "tier": sub.tier.value,
        "status": sub.status.value,
        "stripe_subscription_id": sub.stripe_subscription_id,
        "stripe_customer_id": sub.stripe_customer_id,
        "paypal_subscription_id": sub.paypal_subscription_id,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "created_at": sub.created_at.isoformat(),
    })


def _deserialize(raw: str) -> Subscription | None:
    data = json.loads(raw)
    if data is None:
        return None
    period_end = data["current_period_end"]
    return Subscription(
        id=UUID(data["id"]),
        user_id=UUID(data["user_id"]),
        tier=SubscriptionTier(data["tier"]),
        status=SubscriptionStatus(data["status"]),
        stripe_subscription_id=data["stripe_subscription_id"],
        stripe_customer_id=data["stripe_customer_id"],
        paypal_subscription_id=data["paypal_subscription_id"],
        current_period_end=datetime.fromisoformat(period_end) if period_end else None,
        created_at=datetime.fromisoformat(data["created_at"]),
    )


async def invalidate_subscription(user_id: str) -> None:
    """Drop a user's cached subscription so the next read hits Postgres.

    Called after webhook-driven subscription writes. Best-effort: a Redis
    failure only means the change is visible after CACHE_TTL_SECONDS instead
    of immediately, which must never fail the webhook.
    """
    try:
        await get_redis().delete(_cache_key(user_id))
    except Exception as exc:
        logger.warning(
            "Redis subscription cache invalidate failed for %s "
            "(change visible within %ss): %s",
            user_id, CACHE_TTL_SECONDS, exc,
        )


class CachedSubscriptionRepository:
    """Wraps a subscription repository with Redis cache-aside on reads.

    Only the read path is cached. The write methods are keyed by provider
    subscription id rather than user_id, so they cannot invalidate a
    user_id-keyed entry without an extra lookup; invalidation is instead
    driven from the billing service, where the user_id is already known.
    """

    def __init__(self, underlying):
        self._underlying = underlying
        self._redis = get_redis()

    async def get_subscription_by_user(self, user_id: str) -> Subscription | None:
        cache_key = _cache_key(user_id)
        try:
            cached = await self._redis.get(cache_key)
            if cached is not None:
                return _deserialize(cached)
        except Exception as exc:
            logger.warning(
                "Redis subscription cache read failed, falling back to DB: %s", exc
            )

        sub = await self._underlying.get_subscription_by_user(user_id)
        try:
            await self._redis.setex(cache_key, CACHE_TTL_SECONDS, _serialize(sub))
        except Exception as exc:
            logger.warning("Redis subscription cache write failed: %s", exc)
        return sub
