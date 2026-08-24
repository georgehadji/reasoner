"""
Quota Service — Application-layer orchestrator for usage limits.

Enforces business rules:
- Free tier: 20 queries/month
- Pro tier: 500 queries/month
- Enterprise tier: unlimited (-1)
"""

from __future__ import annotations

from datetime import UTC

from reasoner.application.ports.quota_repository import QuotaRepository
from reasoner.domain.saas import (
    QuotaResult,
    SubscriptionTier,
)

TIER_LIMITS: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 20,
    SubscriptionTier.PRO: 500,
    SubscriptionTier.ENTERPRISE: -1,   # unlimited
}


class QuotaService:
    """Orchestrates quota checks with business-rule enforcement."""

    def __init__(self, repository: QuotaRepository):
        self._repository = repository

    async def check(
        self,
        user_id: str,
        tier: SubscriptionTier,
    ) -> QuotaResult:
        """
        Determine whether a query is allowed under the user's tier.

        Does NOT increment usage — call increment() separately after
        a successful pipeline run to avoid charging for failed runs.
        """
        limit = TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.FREE])

        if limit == -1:
            return QuotaResult(allowed=True, remaining=-1)

        quota = await self._repository.get_quota(user_id)

        # Auto-reset if we've crossed into a new month
        from datetime import datetime
        now = datetime.now(UTC)
        current_period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if quota.period_start < current_period_start:
            await self._repository.reset_monthly(user_id)
            quota = await self._repository.get_quota(user_id)

        remaining = max(0, quota.max_queries - quota.used_queries)
        if remaining <= 0:
            return QuotaResult(
                allowed=False,
                remaining=0,
                retry_after=self._seconds_until_month_end(),
                reason=f"Quota exceeded: {quota.used_queries}/{quota.max_queries} queries used this period.",
            )

        return QuotaResult(allowed=True, remaining=remaining)

    async def increment(self, user_id: str, preset: str = "") -> QuotaResult:
        """
        Increment used_queries by 1 after a successful pipeline run.

        ⚠️ CRITICAL (Enhancement 1.2): This was a no-op stub. Now delegates to repository.
        Must include idempotency key to prevent double-counting on retries.
        """
        return await self._repository.check_and_increment(user_id, preset=preset)

    def _seconds_until_month_end(self) -> int:
        """Rough estimate for Retry-After header."""
        from datetime import datetime, timedelta
        now = datetime.now(UTC)
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        return int((next_month - now).total_seconds())
