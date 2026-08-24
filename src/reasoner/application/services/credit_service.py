"""
Credit Service — application-layer orchestrator for prepaid usage credits.

Business rules enforced here:
- A run may only start when the balance is above the overdraft floor.
- A run is charged *after* it completes, from its actual model spend, so a
  failed run costs nothing.
- Every charge carries an idempotency key so an SSE reconnect or a retried
  webhook cannot double-charge.
- Each billing period grants the subscription tier's allowance exactly once.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reasoner.core.ports.credit_repository import CreditRepository
from reasoner.domain.credits import (
    CreditBalance,
    CreditLedgerEntry,
    CreditReason,
    InsufficientCreditsError,
    can_afford,
    monthly_allowance,
    usd_to_credits,
)
from reasoner.domain.saas import SubscriptionTier

logger = logging.getLogger(__name__)


def current_period_key(now: datetime | None = None) -> str:
    """Billing period identifier used to make monthly grants idempotent."""
    moment = now or datetime.now(UTC)
    return f"{moment.year:04d}-{moment.month:02d}"


class CreditService:
    """Orchestrates balance checks, grants, and metered charges."""

    def __init__(self, repository: CreditRepository):
        self._repository = repository

    # ── Reads ──────────────────────────────────────────────────────────

    async def get_balance(self, user_id: str) -> CreditBalance:
        return await self._repository.get_balance(user_id)

    async def list_ledger(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        return await self._repository.list_entries(user_id, limit=limit, offset=offset)

    async def has_credits_for(self, user_id: str, estimated_cost: int = 1) -> bool:
        """Pre-flight check: can this user afford at least ``estimated_cost``?"""
        balance = await self._repository.get_balance(user_id)
        return can_afford(balance.balance, estimated_cost)

    # ── Grants ─────────────────────────────────────────────────────────

    async def grant(
        self,
        user_id: str,
        credits: int,
        reason: CreditReason,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> CreditLedgerEntry:
        """Add credits to an account. ``credits`` must be positive."""
        if credits <= 0:
            raise ValueError("Grant amount must be positive.")
        return await self._repository.record(
            user_id,
            delta=credits,
            reason=reason,
            reference_id=reference_id,
            description=description,
            allow_overdraft=True,
        )

    async def ensure_monthly_allowance(
        self,
        user_id: str,
        tier: SubscriptionTier,
        now: datetime | None = None,
    ) -> CreditLedgerEntry | None:
        """Grant this period's tier allowance if it has not been granted yet.

        Returns None when the allowance was already granted for the period.
        """
        return await self._repository.grant_monthly_allowance(
            user_id,
            credits=monthly_allowance(tier),
            period_key=current_period_key(now),
        )

    # ── Charges ────────────────────────────────────────────────────────

    async def charge_usd(
        self,
        user_id: str,
        cost_usd: float,
        reference_id: str,
        reason: CreditReason = CreditReason.PIPELINE_RUN,
        description: str | None = None,
    ) -> CreditLedgerEntry | None:
        """Settle a completed unit of work priced in USD.

        Returns None when the work was free (zero cost), which happens for
        cache hits and for runs that failed before any model call.

        Settlement allows overdraft: the work is already done, so the honest
        record is a negative balance rather than a silently discarded charge.
        The next pre-flight check will block the account.
        """
        credits = usd_to_credits(cost_usd)
        if credits <= 0:
            return None
        return await self._repository.record(
            user_id,
            delta=-credits,
            reason=reason,
            reference_id=reference_id,
            description=description,
            allow_overdraft=True,
        )

    async def charge(
        self,
        user_id: str,
        credits: int,
        reference_id: str,
        reason: CreditReason = CreditReason.PIPELINE_RUN,
        description: str | None = None,
    ) -> CreditLedgerEntry:
        """Charge a known credit amount up front, refusing to overdraw.

        Raises:
            InsufficientCreditsError: when the balance cannot cover the charge.
        """
        if credits <= 0:
            raise ValueError("Charge amount must be positive.")
        return await self._repository.record(
            user_id,
            delta=-credits,
            reason=reason,
            reference_id=reference_id,
            description=description,
            allow_overdraft=False,
        )

    async def refund(
        self,
        user_id: str,
        credits: int,
        reference_id: str,
        description: str | None = None,
    ) -> CreditLedgerEntry:
        """Return credits for work that was charged but not delivered."""
        if credits <= 0:
            raise ValueError("Refund amount must be positive.")
        return await self._repository.record(
            user_id,
            delta=credits,
            reason=CreditReason.REFUND,
            reference_id=reference_id,
            description=description,
            allow_overdraft=True,
        )


__all__ = [
    "CreditService",
    "InsufficientCreditsError",
    "current_period_key",
]
