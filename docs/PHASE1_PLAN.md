# Phase 1 Implementation Plan — Foundation: Domain + Ports + Postgres Schema

> **Goal:** Establish the architectural skeleton for SaaS. Zero runtime impact on existing code.  
> **Duration:** 5 working days (Week 1)  
> **Deliverable:** Domain entities, application ports/services, Alembic migration, and additive `PipelinePreset` metadata.  
> **Constraint:** All existing tests (`pytest tests/`) must continue to pass. No existing production code paths are modified except `presets.py` (additive field only).

---

## 0. Pre-Flight Checklist

Before writing code, verify the following baseline:

```bash
# 1. Run the full test suite — capture baseline
python -m pytest tests/ --tb=short -q
# Expected: 443 passed, 303 skipped (or current green state)

# 2. Verify PostgreSQL is available locally (for migration testing)
psql --version
# OR: docker run --name reasoner-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16-alpine

# 3. Verify Python packages
pip list | grep -E "(sqlalchemy|alembic|asyncpg|psycopg)"
# If missing: pip install sqlalchemy alembic asyncpg
```

---

## 1. Directory Structure to Create

```
src/reasoner/
├── domain/
│   ├── __init__.py              # Exports: User, Subscription, UsageQuota, QueryAuditLog, QuotaResult, SubscriptionTier, SubscriptionStatus
│   └── saas.py                  # All SaaS domain entities (frozen dataclasses, zero imports from infrastructure)
│
├── application/
│   ├── ports/
│   │   ├── __init__.py          # Exports: AuthPort, BillingPort, QuotaRepository
│   │   ├── auth_port.py         # Protocol: authenticate(token) -> User
│   │   ├── billing_port.py      # Protocol: checkout, portal, sync_subscription
│   │   └── quota_repository.py  # Protocol: get_quota, check_and_increment, reset_monthly, log_query
│   │
│   └── services/
│       ├── __init__.py          # Exports: AuthService, QuotaService, BillingService, AuditService
│       ├── auth_service.py      # Thin orchestration over AuthPort + caching logic
│       ├── quota_service.py     # Business rules: tier limits, unlimited logic
│       ├── billing_service.py   # Checkout + portal session orchestration
│       └── audit_service.py     # Fire-and-forget query logging via EventBus
│
└── core/events/
    └── domain_events.py         # ADD: SaaS event types (see Section 5)
```

**Rationale:** This mirrors the existing `infrastructure/llm/ports.py` pattern and respects the Dependency Rule. Domain knows nothing about FastAPI, Supabase, Stripe, or Redis.

---

## 2. Day-by-Day Implementation Schedule

### Day 1 — Domain Entities + Event Types

**Files:**
- `src/reasoner/domain/__init__.py`
- `src/reasoner/domain/saas.py`
- `src/reasoner/core/events/domain_events.py` (additive changes)

**Task 2.1.1 — Create `src/reasoner/domain/saas.py`**

This file must have **zero dependencies** on infrastructure (no FastAPI, no SQLAlchemy, no Redis, no Supabase). It depends only on the Python standard library.

```python
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
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
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
    display_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Subscription:
    """A user's subscription plan. Frozen for immutability consistency."""
    id: UUID
    user_id: UUID
    tier: SubscriptionTier
    status: SubscriptionStatus
    stripe_subscription_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None  # NEW: Store Stripe customer ID (Enhancement 4.4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class UsageQuota:
    """Per-user query quota, reset monthly."""
    user_id: UUID
    tier: SubscriptionTier
    used_queries: int = 0
    max_queries: int = 20          # -1 means unlimited
    period_start: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class QuotaResult:
    """Result of a quota check."""
    allowed: bool
    remaining: int
    retry_after: Optional[int] = None   # seconds until reset (computed from period_start + 1 month)
    reason: Optional[str] = None
```

**Task 2.1.2 — Create `src/reasoner/domain/__init__.py`**

```python
from reasoner.domain.saas import (
    SubscriptionTier,
    SubscriptionStatus,
    User,
    Subscription,
    UsageQuota,
    QueryAuditLog,
    QuotaResult,
)

__all__ = [
    "SubscriptionTier",
    "SubscriptionStatus",
    "User",
    "Subscription",
    "UsageQuota",
    "QueryAuditLog",
    "QuotaResult",
]
```

**Task 2.1.3 — Extend `src/reasoner/core/events/domain_events.py`**

Add the following to the `EventType` enum (preserving existing entries):

```python
    # SaaS Events
    USER_REGISTERED = "user_registered"
    USER_LOGGED_IN = "user_logged_in"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    QUOTA_EXCEEDED = "quota_exceeded"
    QUOTA_RESET = "quota_reset"
    QUERY_LOGGED = "query_logged"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"
```

**Day 1 Acceptance Criteria:**
- [ ] `python -c "from reasoner.domain import User, SubscriptionTier; print(User.__dataclass_fields__.keys())"` returns correct fields.
- [ ] `python -c "from reasoner.core.events.domain_events import EventType; print(EventType.SUBSCRIPTION_CREATED)"` works.
- [ ] Existing pytest suite still passes.

---

### Day 2 — Application Ports (Protocols)

**Files:**
- `src/reasoner/application/ports/__init__.py`
- `src/reasoner/application/ports/auth_port.py`
- `src/reasoner/application/ports/billing_port.py`
- `src/reasoner/application/ports/quota_repository.py`

**Task 2.2.1 — Auth Port**

```python
"""
Auth Port — Abstract interface for authentication providers.

The domain and application layers depend ONLY on this protocol.
Concrete adapters (Supabase, Auth0, local JWT) implement this interface.
"""

from __future__ import annotations

from typing import Protocol
from reasoner.domain.saas import User


class AuthPort(Protocol):
    """Port for user authentication."""

    async def authenticate(self, token: str) -> User:
        """
        Validate a bearer token and return the canonical User entity.

        Raises:
            AuthenticationError: If token is invalid, expired, or malformed.
        """
        ...

    async def refresh_session(self, token: str) -> str:
        """
        Refresh an access token if supported by the provider.

        Returns:
            New access token string.
        """
        ...
```

**Task 2.2.2 — Billing Port**

```python
"""
Billing Port — Abstract interface for payment providers.

Stripe is the default adapter, but the domain never imports stripe.
"""

from __future__ import annotations

from typing import Protocol
from reasoner.domain.saas import Subscription, SubscriptionTier


class BillingPort(Protocol):
    """Port for subscription billing operations."""

    async def create_checkout_session(
        self,
        user_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Return a checkout URL for the user to complete payment."""
        ...

    async def create_portal_session(self, user_id: str, return_url: str) -> str:
        """Return a billing portal URL for self-service management."""
        ...

    async def sync_subscription(self, provider_event: dict) -> Subscription:
        """
        Idempotently sync a subscription from a provider webhook event.

        Args:
            provider_event: Raw event payload (e.g., Stripe webhook JSON).

        Returns:
            Canonical Subscription entity reflecting the latest state.
        """
        ...
```

**Task 2.2.3 — Quota Repository Port**

```python
"""
Quota Repository Port — Abstract interface for quota persistence.

Implementations may use PostgreSQL, Redis, or a hybrid cache-aside strategy.
"""

from __future__ import annotations

from typing import Protocol
from reasoner.domain.saas import UsageQuota, QuotaResult


class QuotaRepository(Protocol):
    """Port for usage quota storage and enforcement."""

    async def get_quota(self, user_id: str) -> UsageQuota:
        """Fetch the current quota for a user."""
        ...

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        """
        Atomically check remaining quota and increment used_queries by 1.

        This MUST be transactional (SELECT ... FOR UPDATE or equivalent)
        to prevent race conditions under concurrent requests.
        """
        ...

    async def reset_monthly(self, user_id: str) -> None:
        """Reset used_queries to 0 and update period_start to current month."""
        ...

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Append an immutable entry to the query audit log."""
        ...
```

**Task 2.2.4 — Create `src/reasoner/application/ports/__init__.py`**

```python
from reasoner.application.ports.auth_port import AuthPort
from reasoner.application.ports.billing_port import BillingPort
from reasoner.application.ports.quota_repository import QuotaRepository

__all__ = ["AuthPort", "BillingPort", "QuotaRepository"]
```

**Day 2 Acceptance Criteria:**
- [ ] `python -c "from reasoner.application.ports import AuthPort, BillingPort, QuotaRepository; print('OK')"` succeeds.
- [ ] `mypy src/reasoner/application/ports/` passes with no errors (if mypy is configured).
- [ ] Existing pytest suite still passes.

---

### Day 3 — Application Services

**Files:**
- `src/reasoner/application/services/__init__.py`
- `src/reasoner/application/services/quota_service.py`
- `src/reasoner/application/services/auth_service.py`
- `src/reasoner/application/services/billing_service.py`
- `src/reasoner/application/services/audit_service.py`

**Task 2.3.1 — Quota Service (most critical)**

```python
"""
Quota Service — Application-layer orchestrator for usage limits.

Enforces business rules:
- Free tier: 20 queries/month
- Pro tier: 500 queries/month
- Enterprise tier: unlimited (-1)
"""

from __future__ import annotations

from reasoner.domain.saas import (
    SubscriptionTier,
    UsageQuota,
    QuotaResult,
)
from reasoner.application.ports.quota_repository import QuotaRepository


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
        preset: str,
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
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

    async def increment(self, user_id: str) -> QuotaResult:
        """
        Increment used_queries by 1 after a successful pipeline run.
        
        ⚠️ CRITICAL (Enhancement 1.2): This was a no-op stub. Now delegates to repository.
        Must include idempotency key to prevent double-counting on retries.
        """
        return await self._repository.check_and_increment(user_id, preset="")

    def _seconds_until_month_end(self) -> int:
        """Rough estimate for Retry-After header."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        return int((next_month - now).total_seconds())
```

**Task 2.3.2 — Auth Service**

```python
"""
Auth Service — Thin wrapper over AuthPort with caching and logging.
"""

from __future__ import annotations

from reasoner.domain.saas import User
from reasoner.application.ports.auth_port import AuthPort


class AuthService:
    def __init__(self, port: AuthPort):
        self._port = port

    async def authenticate(self, token: str) -> User:
        # Future: add Redis cache here (TTL = JWT expiry - 60s)
        return await self._port.authenticate(token)

    async def refresh_session(self, token: str) -> str:
        return await self._port.refresh_session(token)
```

**Task 2.3.3 — Billing Service**

```python
"""
Billing Service — Orchestrates checkout, portal, and webhook sync.
"""

from __future__ import annotations

from reasoner.domain.saas import SubscriptionTier
from reasoner.application.ports.billing_port import BillingPort


class BillingService:
    def __init__(self, port: BillingPort):
        self._port = port

    async def create_checkout(
        self,
        user_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        return await self._port.create_checkout_session(user_id, tier, success_url, cancel_url)

    async def create_portal(self, user_id: str, return_url: str) -> str:
        return await self._port.create_portal_session(user_id, return_url)

    async def handle_webhook(self, event: dict) -> None:
        """Idempotent webhook processing."""
        await self._port.sync_subscription(event)
```

**Task 2.3.4 — Audit Service**

```python
"""
Audit Service — Logs query executions as domain events.

Publishes to the EventBus so the hot pipeline path is never blocked by I/O.
"""

from __future__ import annotations

import time
from uuid import uuid4

from reasoner.application.event_bus.bus import EventBus
from reasoner.core.events.domain_events import DomainEvent, EventType


class AuditService:
    def __init__(self, event_bus: EventBus):
        self._bus = event_bus

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        event = DomainEvent(
            event_id=str(uuid4()),
            event_type=EventType.QUERY_LOGGED,
            timestamp=time.time(),
            aggregate_id=user_id,
            version=1,
            metadata={
                "preset": preset,
                "method": method,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )
        await self._bus.publish(event)
```

**Task 2.3.5 — Create `src/reasoner/application/services/__init__.py`**

```python
from reasoner.application.services.auth_service import AuthService
from reasoner.application.services.quota_service import QuotaService
from reasoner.application.services.billing_service import BillingService
from reasoner.application.services.audit_service import AuditService

__all__ = ["AuthService", "QuotaService", "BillingService", "AuditService"]
```

**Day 3 Acceptance Criteria:**
- [ ] `python -c "from reasoner.application.services import QuotaService, AuthService, BillingService, AuditService; print('OK')"` succeeds.
- [ ] Unit test `test_quota_service_unlimited_enterprise` passes.
- [ ] Unit test `test_quota_service_free_blocks_at_20` passes (mocked repository).
- [ ] Existing pytest suite still passes.

---

### Day 4 — Preset Tier Metadata + Migration

**Files:**
- `src/reasoner/presets.py` (additive change)
- `migrations/` directory setup
- `migrations/versions/001_saas_init.py` (Alembic) OR `migrations/001_saas_init.sql` (raw SQL)

**Task 2.4.1 — Add `required_tier` to `PipelinePreset`**

In `src/reasoner/presets.py`, modify the `PipelinePreset` dataclass:

```python
from reasoner.domain.saas import SubscriptionTier   # NEW import

@dataclass
class PipelinePreset:
    """A named routing configuration with metadata."""
    name: str
    description: str
    primary_id: str
    routing: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)
    phase_overrides: "dict[str, PhaseConfig]" = field(default_factory=dict)
    fallback_routing: dict[str, str] = field(default_factory=dict)
    required_tier: SubscriptionTier = SubscriptionTier.FREE   # NEW — additive, default FREE

    def __post_init__(self) -> None:
        # existing validation unchanged
        ...
```

Then update `_PRESET_CONFIGS` entries for premium presets. Example for `multi-perspective-premium`:

```python
    {
        "id": "multi-perspective-premium",
        ...
        "required_tier": SubscriptionTier.PRO,   # NEW
    },
```

Add a helper function:

```python
def get_preset_tier(preset_id: str) -> SubscriptionTier:
    """Return the minimum subscription tier required for a preset."""
    preset = PRESETS.get(preset_id)
    if preset is None:
        return SubscriptionTier.FREE
    return preset.required_tier
```

**Task 2.4.2 — Set up Alembic (if not already present)**

```bash
# From project root
pip install alembic
alembic init migrations
```

Configure `migrations/env.py` to use asyncpg:

```python
# migrations/env.py — key snippets
from sqlalchemy.ext.asyncio import create_async_engine
from reasoner.core.settings import settings

config = context.config
target_metadata = None  # We use raw SQL migrations for now to avoid SQLAlchemy model sync complexity

async def run_migrations_online():
    connectable = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
```

**Task 2.4.3 — Write Migration `migrations/versions/001_saas_init.py`**

```python
"""SaaS foundation schema

Revision ID: 001
Revises:
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001_saas_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ⚠️ CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 1.4, 1.6, 1.7, 1.8, 1.9):
    # 1.4: Add FK to auth.users(id) for Supabase Auth integration
    # 1.6: Add NOT NULL constraints on tier, status columns
    # 1.7: Add CHECK constraints for enum validation
    # 1.8: Use BRIN index (not B-tree) for append-only time-series table
    # 1.9: Use UPSERT (INSERT...ON CONFLICT) to prevent TOCTOU race in get_quota
    
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # Enhancement 1.4: FK constraint to Supabase auth.users(id) with CASCADE delete
        sa.ForeignKeyConstraint(["id"], ["auth.users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),  # Enhancement 1.6: NOT NULL
        sa.Column("status", sa.Text(), nullable=False),  # Enhancement 1.6: NOT NULL
        sa.Column("stripe_sub_id", sa.Text(), nullable=True),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),  # Enhancement 4.4: Store customer ID
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_sub_id"),
        sa.UniqueConstraint("stripe_customer_id"),  # Enhancement 4.4
        # Enhancement 1.7: CHECK constraints for enum validation
        sa.CheckConstraint("tier IN ('free','pro','enterprise')", name="check_tier"),
        sa.CheckConstraint("status IN ('active','cancelled','past_due','trialing')", name="check_status"),
    )
    op.create_index("idx_subscriptions_user", "subscriptions", ["user_id"])

    op.create_table(
        "usage_quotas",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("used_queries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_queries", sa.Integer(), server_default="20", nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), server_default=sa.text("date_trunc('month', now())"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "query_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("preset", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_query_log_user", "query_log", ["user_id", "created_at"])
    # Enhancement 1.8: BRIN index for time-series (10x smaller, faster on append-only tables)
    op.execute("CREATE INDEX idx_query_log_created_brin ON query_log USING BRIN (created_at)")


def downgrade() -> None:
    op.drop_index("idx_query_log_created", table_name="query_log")
    op.drop_index("idx_query_log_user", table_name="query_log")
    op.drop_table("query_log")
    op.drop_table("usage_quotas")
    op.drop_index("idx_subscriptions_user", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("user_profiles")
```

**Alternative (if Alembic setup is deferred):** Create `migrations/001_saas_init.sql` for manual execution.

**Task 2.4.4 — Add `DATABASE_URL` to settings**

In `src/reasoner/core/settings.py`, add:

```python
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/reasoner"
)
```

**Day 4 Acceptance Criteria:**
- [ ] `alembic upgrade head` applies cleanly to a fresh Postgres database.
- [ ] `alembic downgrade -1` reverts cleanly.
- [ ] `python -c "from reasoner.presets import get_preset_tier; print(get_preset_tier('multi-perspective-premium'))"` returns `SubscriptionTier.PRO`.
- [ ] `python -c "from reasoner.presets import get_preset_tier; print(get_preset_tier('multi-perspective-budget'))"` returns `SubscriptionTier.FREE`.
- [ ] Existing pytest suite still passes.

---

### Day 5 — Tests + Integration Validation

**Files:**
- `tests/test_saas_domain.py`
- `tests/test_saas_quota_service.py`
- `tests/test_saas_preset_tiers.py`

**Task 2.5.1 — Domain Unit Tests**

```python
# tests/test_saas_domain.py
import pytest
from uuid import uuid4
from reasoner.domain.saas import (
    SubscriptionTier,
    SubscriptionStatus,
    User,
    Subscription,
    UsageQuota,
    QuotaResult,
)


class TestSubscriptionTier:
    def test_tier_values(self):
        assert SubscriptionTier.FREE.value == "free"
        assert SubscriptionTier.PRO.value == "pro"
        assert SubscriptionTier.ENTERPRISE.value == "enterprise"


class TestUser:
    def test_user_is_frozen(self):
        user = User(id=uuid4(), email="test@example.com")
        with pytest.raises(AttributeError):
            user.email = "other@example.com"


class TestQuotaResult:
    def test_allowed_result(self):
        qr = QuotaResult(allowed=True, remaining=5)
        assert qr.allowed is True
        assert qr.remaining == 5

    def test_denied_result(self):
        qr = QuotaResult(allowed=False, remaining=0, retry_after=3600, reason="Exceeded")
        assert qr.allowed is False
        assert qr.retry_after == 3600
```

**Task 2.5.2 — Quota Service Unit Tests (Mocked Repository)**

```python
# tests/test_saas_quota_service.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from reasoner.domain.saas import SubscriptionTier, UsageQuota, QuotaResult
from reasoner.application.services.quota_service import QuotaService


class FakeQuotaRepository:
    def __init__(self, quota: UsageQuota):
        self.quota = quota

    async def get_quota(self, user_id: str) -> UsageQuota:
        return self.quota

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        remaining = max(0, self.quota.max_queries - self.quota.used_queries)
        allowed = remaining > 0
        return QuotaResult(allowed=allowed, remaining=remaining)

    async def reset_monthly(self, user_id: str) -> None:
        self.quota.used_queries = 0
        self.quota.period_start = datetime.now(timezone.utc).replace(day=1)


@pytest.mark.asyncio
async def test_quota_service_enterprise_unlimited():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.ENTERPRISE, max_queries=-1)
    )
    service = QuotaService(repo)
    result = await service.check("u1", "debate-premium", SubscriptionTier.ENTERPRISE)
    assert result.allowed is True
    assert result.remaining == -1


@pytest.mark.asyncio
async def test_quota_service_free_blocks_when_exhausted():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=20, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", "debate-budget", SubscriptionTier.FREE)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.reason is not None


@pytest.mark.asyncio
async def test_quota_service_free_allows_when_under_limit():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=5, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", "debate-budget", SubscriptionTier.FREE)
    assert result.allowed is True
    assert result.remaining == 15
```

**Task 2.5.3 — Preset Tier Tests**

```python
# tests/test_saas_preset_tiers.py
import pytest
from reasoner.presets import PRESETS, get_preset_tier
from reasoner.domain.saas import SubscriptionTier


def test_all_budget_presets_are_free():
    for name, preset in PRESETS.items():
        if name.endswith("-budget"):
            assert preset.required_tier == SubscriptionTier.FREE, f"{name} should be FREE"


def test_all_premium_presets_require_pro():
    for name, preset in PRESETS.items():
        if name.endswith("-premium"):
            assert preset.required_tier == SubscriptionTier.PRO, f"{name} should be PRO"


def test_get_preset_tier_unknown_preset_defaults_free():
    assert get_preset_tier("nonexistent-preset") == SubscriptionTier.FREE
```

**Task 2.5.4 — Run Full Regression**

```bash
python -m pytest tests/ --tb=short -q
```

**Day 5 Acceptance Criteria:**
- [ ] `tests/test_saas_domain.py` passes.
- [ ] `tests/test_saas_quota_service.py` passes.
- [ ] `tests/test_saas_preset_tiers.py` passes.
- [ ] Full regression suite passes with zero new failures.
- [ ] Code coverage for new SaaS domain + services ≥ 90%.

---

## 3. Files Changed Summary

| File | Change Type | Blast Radius |
|---|---|---|
| `src/reasoner/domain/saas.py` | **New** | None (new module) |
| `src/reasoner/domain/__init__.py` | **New** | None |
| `src/reasoner/application/ports/*.py` | **New** | None |
| `src/reasoner/application/services/*.py` | **New** | None |
| `src/reasoner/core/events/domain_events.py` | **Add** enum variants | Low — additive only |
| `src/reasoner/presets.py` | **Add** `required_tier` field + helper | Low — additive default |
| `src/reasoner/core/settings.py` | **Add** `DATABASE_URL` | Low — env var only |
| `migrations/versions/001_saas_init.py` | **New** | None (infra) |
| `tests/test_saas_*.py` | **New** | None |

---

## 4. Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| **Pure dataclasses in domain** | No SQLAlchemy, no Pydantic. Keeps domain independent and testable without a database. |
| **`required_tier` defaults to `FREE`** | Existing presets behave identically without explicit changes. Only premium presets need tagging. |
| **Quota check and increment are separate** | Prevents charging users for failed pipeline runs. Check before execution; increment after success. |
| **Audit uses EventBus, not direct DB write** | Keeps the hot pipeline path non-blocking. Handler can write to Postgres asynchronously. |
| **Alembic for migrations** | Industry standard; supports rollback; integrates with CI. |
| **No Stripe/Supabase imports yet** | Phase 1 is skeleton only. Adapters come in Phase 2–4. This keeps PR reviews focused. |

---

## 5. Risk Mitigation

| Risk | Mitigation |
|---|---|
| **Circular import** `domain` → `core/events` | `domain_events.py` already exists in `core/`. `domain/saas.py` only imports `datetime`/`enum`/`uuid` — no dependency on `core/events`. |
| **Presets.py import of `SubscriptionTier` creates dependency from Domain → Presets** | Actually `presets.py` imports FROM `domain`. This is correct: Domain is at the center. Presets (application/domain config) may depend on Domain. |
| **Alembic conflicts with existing DB** | Migration is `revision = "001"` with `down_revision = None`. If a DB already has tables, Alembic should be configured with `baseline` first. |
| **Test suite slowdown** | New tests are pure unit tests (no DB, no HTTP). Expected runtime < 2 seconds. |

---

## 6. Handoff to Phase 2

After Phase 1 is complete, the following **interfaces** are ready for implementation:

1. `AuthPort` → `SupabaseAuthAdapter` (Phase 2)
2. `QuotaRepository` → `PostgresQuotaRepository` + Redis cache (Phase 3)
3. `BillingPort` → `StripeBillingAdapter` (Phase 4)
4. `EventBus` subscriber → `QueryLogHandler` (writes to `query_log` table) (Phase 3)

The **domain vocabulary** is established:
- `User`, `Subscription`, `UsageQuota`, `QueryAuditLog`, `QuotaResult`
- `SubscriptionTier.FREE/PRO/ENTERPRISE`
- `EventType.QUERY_LOGGED`, `EventType.SUBSCRIPTION_UPDATED`, etc.

All subsequent phases build **adapters** and **wiring** against these stable interfaces — never modifying the domain.

---

*End of Phase 1 Plan*
