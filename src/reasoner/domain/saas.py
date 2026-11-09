"""
SaaS Domain Entities

Pure dataclasses representing the billing, auth, and quota domain.
These entities know nothing about HTTP, databases, or third-party APIs.

⚠️ CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 1.1–1.5):
- Use datetime.now(timezone.utc) instead of deprecated datetime.utcnow()
- Freeze Subscription dataclass for consistency with User and QuotaResult
- Add __slots__ to frequently-instantiated entities (User, QuotaResult) for ~40 bytes savings per instance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from uuid import UUID


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


@dataclass(frozen=True, slots=True)
class User:
    """Canonical user entity — auth-provider agnostic."""
    id: UUID
    email: str
    display_name: str | None = None
    scopes: set[str] = field(default_factory=set)
    auth_provider: str | None = None
    avatar_url: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: Set when the caller authenticated with a Reasoner API key, so admission
    #: can record that this key started a run (audit 5 SEC-19, Q1).
    api_key_id: UUID | None = None


@dataclass(frozen=True)
class Subscription:
    """A user's subscription plan. Frozen for immutability consistency."""
    id: UUID
    user_id: UUID
    tier: SubscriptionTier
    status: SubscriptionStatus
    stripe_subscription_id: str | None = None
    current_period_end: datetime | None = None
    stripe_customer_id: str | None = None  # NEW: Store Stripe customer ID (Enhancement 4.4)
    paypal_subscription_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class UnresolvedBillingOwnerError(Exception):
    """A provider event names no user we can find.

    Raised by an adapter instead of inventing an owner: the old fallback minted
    a random UUID, so a cancellation "applied" to nobody and a payment failure
    wrote quota rows for a user that does not exist. The webhook receiver
    dead-letters the event once and acknowledges it, because a retry cannot
    resolve it either (docs/plans/audit-remediation-2-2026-10-20.md BIL-13).
    """


class CheckoutDecision(StrEnum):
    ALLOW = "allow"
    USE_PORTAL = "use_portal"   # change plan in the provider's portal (prorated)
    SAME_PLAN = "same_plan"


#: Statuses in which the provider is still billing, or about to.
LIVE_STATUSES = frozenset({
    SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE,
})


def checkout_allowed(
    existing: Subscription | None, target: SubscriptionTier
) -> CheckoutDecision:
    """Whether a new checkout may start, given the user's latest subscription.

    A second checkout created a second live subscription that overwrote the
    first one's row, so the first kept billing untracked
    (docs/plans/audit-remediation-2-2026-10-20.md BIL-14). A user who already
    pays changes plan in the portal instead (Q4).
    """
    if (
        existing is None
        or existing.status not in LIVE_STATUSES
        or existing.tier == SubscriptionTier.FREE
    ):
        return CheckoutDecision.ALLOW
    return CheckoutDecision.SAME_PLAN if existing.tier == target else CheckoutDecision.USE_PORTAL


@dataclass(frozen=True)
class UsageQuota:
    """Per-user query quota, reset monthly."""
    user_id: UUID
    tier: SubscriptionTier
    used_queries: int = 0
    max_queries: int = 20          # -1 means unlimited
    period_start: datetime = field(
        default_factory=lambda: datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class QueryAuditLog:
    """Immutable record of a single pipeline execution."""
    id: UUID
    user_id: UUID
    preset: str
    method: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class QuotaResult:
    """Result of a quota check."""
    allowed: bool
    remaining: int
    retry_after: int | None = None   # seconds until reset (computed from period_start + 1 month)
    reason: str | None = None
