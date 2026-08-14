"""
Credits Domain — prepaid usage currency for metered pipeline runs.

Pure domain: no HTTP, no database, no third-party APIs. Everything here is
deterministic and unit-testable without infrastructure.

Model
-----
A *credit* is the smallest billable unit the product exposes. One credit is
worth ``1 / CREDITS_PER_USD`` of underlying model spend, so credit amounts are
integers and can never accumulate floating-point drift across a ledger.

The ledger is append-only. Balance is a materialised projection of the ledger,
and every entry records ``balance_after`` so a balance can be audited without
replaying the whole history.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from reasoner.domain.saas import SubscriptionTier


# 1 credit = $0.001 USD of model spend. A budget run (~$0.02) costs ~20 credits,
# a premium run (~$0.20) costs ~200 credits.
CREDITS_PER_USD = 1000

# Monthly allowance granted per tier at the start of each billing period.
TIER_MONTHLY_CREDITS: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 500,
    SubscriptionTier.PRO: 25_000,
    SubscriptionTier.ENTERPRISE: 250_000,
}

# Synchronous charges must leave the balance at or above this floor. Post-run
# settlement is exempt (it charges work already performed and may push the
# balance negative); the next pre-flight check then blocks further runs.
MAX_OVERDRAFT_CREDITS = 0


class CreditReason(str, Enum):
    """Why a ledger entry exists. Persisted — do not renumber or rename."""

    SIGNUP_BONUS = "signup_bonus"
    MONTHLY_GRANT = "monthly_grant"
    PURCHASE = "purchase"
    ADMIN_ADJUSTMENT = "admin_adjustment"
    REFUND = "refund"
    PIPELINE_RUN = "pipeline_run"
    IMAGE_GENERATION = "image_generation"
    WEB_SEARCH = "web_search"


#: Reasons that add credits. Everything else removes them.
_CREDIT_REASONS = frozenset(
    {
        CreditReason.SIGNUP_BONUS,
        CreditReason.MONTHLY_GRANT,
        CreditReason.PURCHASE,
        CreditReason.ADMIN_ADJUSTMENT,
        CreditReason.REFUND,
    }
)


def is_grant_reason(reason: CreditReason) -> bool:
    """True when ``reason`` describes credits flowing into an account."""
    return reason in _CREDIT_REASONS


@dataclass(frozen=True, slots=True)
class CreditBalance:
    """A user's current credit position."""

    user_id: UUID
    balance: int = 0
    lifetime_granted: int = 0
    lifetime_spent: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_exhausted(self) -> bool:
        return self.balance <= 0

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "balance": self.balance,
            "balance_usd": round(credits_to_usd(self.balance), 6),
            "lifetime_granted": self.lifetime_granted,
            "lifetime_spent": self.lifetime_spent,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CreditLedgerEntry:
    """One append-only movement of credits."""

    id: UUID
    user_id: UUID
    delta: int                       # positive = granted, negative = spent
    balance_after: int
    reason: CreditReason
    reference_id: Optional[str] = None   # idempotency key, unique per user
    description: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "delta": self.delta,
            "balance_after": self.balance_after,
            "reason": self.reason.value,
            "reference_id": self.reference_id,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }


class InsufficientCreditsError(Exception):
    """Raised when a charge would take the balance below the overdraft floor."""

    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits: {required} required, {available} available."
        )


def usd_to_credits(cost_usd: float) -> int:
    """Convert model spend in USD to whole credits, always rounding up.

    Rounding up means a run that costs anything at all costs at least one
    credit, so a caller can never execute unbounded free work by staying under
    a fractional threshold.
    """
    if cost_usd <= 0:
        return 0
    return math.ceil(cost_usd * CREDITS_PER_USD)


def credits_to_usd(credits: int) -> float:
    """Convert credits back to their USD face value."""
    return credits / CREDITS_PER_USD


def monthly_allowance(tier: SubscriptionTier) -> int:
    """Credits granted per billing period for ``tier``."""
    return TIER_MONTHLY_CREDITS.get(tier, TIER_MONTHLY_CREDITS[SubscriptionTier.FREE])


def can_afford(balance: int, cost: int) -> bool:
    """Whether ``cost`` can be charged against ``balance`` within the overdraft floor."""
    return balance - cost >= -MAX_OVERDRAFT_CREDITS
