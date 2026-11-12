"""
Quota Service — Application-layer orchestrator for usage limits.

Enforces business rules:
- Free tier: 20 queries/month
- Pro tier: 500 queries/month
- Enterprise tier: unlimited (-1)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum

from reasoner.application.ports.quota_repository import QuotaRepository
from reasoner.core.state_machine import Machine
from reasoner.domain.saas import (
    QuotaResult,
    SubscriptionTier,
)

TIER_LIMITS: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 20,
    SubscriptionTier.PRO: 500,
    SubscriptionTier.ENTERPRISE: -1,   # unlimited
}


class QuotaSlotState(StrEnum):
    """One admission's claim on ``usage_quotas.used_queries`` (SM-M4)."""

    UNCLAIMED = "unclaimed"
    CLAIMED = "claimed"  # check_and_increment took a slot in the current period
    RELEASED = "released"  # given back inside the period it was claimed in
    VOIDED = "voided"  # the monthly reset zeroed the count first; nothing left to give back


#: The claim itself is SELECT ... FOR UPDATE in ``check_and_increment``; the period
#: guard on release is the SQL ``period_start <= claimed_at`` in ``release_slot``.
QUOTA_SLOT_MACHINE = Machine(
    "quota_slot",
    {
        QuotaSlotState.UNCLAIMED: {QuotaSlotState.CLAIMED},
        QuotaSlotState.CLAIMED: {QuotaSlotState.RELEASED, QuotaSlotState.VOIDED},
        QuotaSlotState.RELEASED: set(),
        QuotaSlotState.VOIDED: set(),
    },
    initial=QuotaSlotState.UNCLAIMED,
)


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
        now = datetime.now(UTC)
        current_period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # period_start is nullable and no INSERT path sets it, so a row that has
        # never been reset arrives as None. Treat it as a stale period rather
        # than comparing None to a datetime.
        if quota.period_start is None or quota.period_start < current_period_start:
            await self._repository.reset_monthly(user_id)
            quota = await self._repository.get_quota(user_id)

        # The entitlement tier is a ceiling over the persisted row, not a
        # synonym for it: past_due is a live status (LIVE_STATUSES), so a past-due
        # subscriber keeps the paid tier while the provider retries; max_queries
        # on the row is not re-synced on that event and may disagree with the
        # tier. -1 on the row means unlimited, not a negative cap.
        row_max = limit if quota.max_queries < 0 else quota.max_queries
        effective_max = min(limit, row_max)

        remaining = max(0, effective_max - quota.used_queries)
        if remaining <= 0:
            # Deliberately not counted here: check() is also a read-only status
            # query (GET /quota). The quota-exceeded metric is recorded where the
            # request is actually rejected, in api.dependencies.check_quota.
            return QuotaResult(
                allowed=False,
                remaining=0,
                retry_after=self._seconds_until_month_end(),
                reason=f"Quota exceeded: {quota.used_queries}/{effective_max} queries used this period.",
            )

        return QuotaResult(allowed=True, remaining=remaining)

    async def increment(self, user_id: str, preset: str = "") -> QuotaResult:
        """Take one quota slot, atomically, when a run is admitted (audit 6, finding 3).

        ``check()`` only reads, so N concurrent runs at 19/20 all passed it and each
        counted itself at the end: 24/20. This is the claim that makes the limit
        hard. A denial (``allowed=False``) means the limit was reached; ``remaining
        == -1`` means an unlimited row, which takes no slot and must not be released.
        The run gives the slot back with :meth:`release` if it ends up costing nothing.
        """
        result = await self._repository.check_and_increment(user_id, preset=preset)
        if not result.allowed and result.retry_after is None:
            result = replace(result, retry_after=self._seconds_until_month_end())
        return result

    async def release(self, user_id: str, claimed_at: datetime | None = None) -> None:
        """Give back a slot taken by :meth:`increment` for a run that was not billed.

        Pass the claim time so a release after the month rolled over is a no-op.
        """
        QUOTA_SLOT_MACHINE.move(QuotaSlotState.CLAIMED, QuotaSlotState.RELEASED)
        await self._repository.release_slot(user_id, claimed_at)

    def _seconds_until_month_end(self) -> int:
        """Rough estimate for Retry-After header."""
        from datetime import datetime, timedelta
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        return int((next_month - now).total_seconds())
