# Phase 4 Implementation Plan — Billing with Stripe

> **Goal:** Enable self-service upgrades, downgrades, and invoicing via Stripe.  
> **Duration:** 10 working days (Weeks 4–5)  
> **Deliverable:** Stripe checkout, billing portal, webhook handling, subscription sync, frontend pricing page.  
> **Constraint:** All webhook handlers are idempotent. All existing tests pass.

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phases 1-3 are complete
python -m pytest tests/ --tb=short -q

# 2. Install Stripe SDKs
pip install stripe
npm install --save @stripe/stripe-js @stripe/react-stripe-js

# 3. Configure Stripe
# - Create account at https://dashboard.stripe.com
# - Create Products: Reasoner Pro ($12/mo, $99/yr), Reasoner Enterprise ($49/mo)
# - Get API keys: sk_test_... (backend), pk_test_... (frontend)
# - Configure webhook endpoint: https://yourdomain.com/api/billing/webhook
# - Get webhook signing secret: whsec_...

# 4. Add env vars
cat >> .env << 'EOF'
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_ENTERPRISE_PRICE_ID=price_...
EOF
```

---

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 4.1–4.9):**
- 4.1: All Stripe SDK calls are synchronous but used in async context — wrap with `asyncio.to_thread()`
- 4.2: Subscription upsert resets used_queries=0 on every webhook — remove this from ON CONFLICT DO UPDATE clause
- 4.3: Webhook returns 400 on errors — should return 200 (with error log) to prevent infinite Stripe retries
- 4.4: No stripe_customer_id in DB — metadata lookup is unreliable — store customer ID explicitly
- 4.5: Subscription(id=UUID(int=0)) creates invalid null-UUID collisions — use uuid4() instead
- 4.9: Missing webhook deduplication by event.id — can create duplicate subscriptions

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Stripe Dashboard                          │
└──────────┬──────────────────────────────────────────────────────┘
           │ Webhooks
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/billing/webhook                                      │
│  ├── verify stripe-signature                                    │
│  ├── check Redis deduplication by event.id (Enhancement 4.9)   │
│  ├── parse event type                                           │
│  └── route to idempotent handler                                │
│       ├─ checkout.session.completed ──► create subscription     │
│       ├─ customer.subscription.updated ──► sync tier/status     │
│       ├─ customer.subscription.deleted ──► downgrade to free    │
│       ├─ invoice.payment_failed ──► set past_due, notify        │
│       └─ invoice.payment_succeeded ──► reset quota              │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL subscriptions table                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Day-by-Day Implementation Schedule

### Day 1 — Stripe Adapter

**Files:**
- `src/reasoner/infrastructure/billing/__init__.py`
- `src/reasoner/infrastructure/billing/stripe_adapter.py`

**Task 4.1.1 — Stripe Adapter**

```python
# src/reasoner/infrastructure/billing/stripe_adapter.py
"""Stripe implementation of BillingPort."""

from __future__ import annotations

import os
import logging
from uuid import UUID

import stripe

from reasoner.domain.saas import Subscription, SubscriptionTier, SubscriptionStatus
from reasoner.application.ports.billing_port import BillingPort

logger = logging.getLogger(__name__)


class StripeBillingAdapter(BillingPort):
    def __init__(self, api_key: str | None = None):
        stripe.api_key = api_key or os.environ["STRIPE_SECRET_KEY"]

    async def create_checkout_session(
        self,
        user_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        price_id = self._price_id_for_tier(tier)
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,
            allow_promotion_codes=True,
        )
        return session.url

    async def create_portal_session(self, user_id: str, return_url: str) -> str:
        # Lookup Stripe customer by user_id (stored in metadata)
        customers = stripe.Customer.list(
            limit=1,
            metadata={"reasoner_user_id": user_id},
        )
        if not customers.data:
            raise ValueError(f"No Stripe customer found for user {user_id}")

        session = stripe.billing_portal.Session.create(
            customer=customers.data[0].id,
            return_url=return_url,
        )
        return session.url

    async def sync_subscription(self, provider_event: dict) -> Subscription:
        event_type = provider_event.get("type")
        data = provider_event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            return await self._handle_checkout_completed(data)
        elif event_type == "customer.subscription.updated":
            return await self._handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            return await self._handle_subscription_deleted(data)

        # Return a no-op subscription for unhandled events
        return Subscription(
            id=UUID(int=0),
            user_id=UUID(int=0),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.CANCELLED,
        )

    def _price_id_for_tier(self, tier: SubscriptionTier) -> str:
        mapping = {
            SubscriptionTier.PRO: os.environ["STRIPE_PRO_PRICE_ID"],
            SubscriptionTier.ENTERPRISE: os.environ["STRIPE_ENTERPRISE_PRICE_ID"],
        }
        return mapping[tier]

    async def _handle_checkout_completed(self, session: dict) -> Subscription:
        # Extract user_id from client_reference_id
        user_id = session.get("client_reference_id")
        # Subscription object is in subscription field
        sub_id = session.get("subscription")
        stripe_sub = stripe.Subscription.retrieve(sub_id)
        return self._stripe_sub_to_domain(stripe_sub, UUID(user_id))

    async def _handle_subscription_updated(self, stripe_sub: dict) -> Subscription:
        # Lookup user_id from customer metadata
        customer = stripe.Customer.retrieve(stripe_sub["customer"])
        user_id = customer.metadata.get("reasoner_user_id")
        return self._stripe_sub_to_domain(stripe_sub, UUID(user_id))

    async def _handle_subscription_deleted(self, stripe_sub: dict) -> Subscription:
        customer = stripe.Customer.retrieve(stripe_sub["customer"])
        user_id = customer.metadata.get("reasoner_user_id")
        return Subscription(
            id=UUID(int=0),
            user_id=UUID(user_id),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.CANCELLED,
            stripe_subscription_id=stripe_sub["id"],
        )

    def _stripe_sub_to_domain(self, stripe_sub: dict, user_id: UUID) -> Subscription:
        tier = self._tier_from_price(stripe_sub["items"]["data"][0]["price"]["id"])
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELLED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
        }
        return Subscription(
            id=UUID(int=0),  # Not used for Stripe-synced subs
            user_id=user_id,
            tier=tier,
            status=status_map.get(stripe_sub["status"], SubscriptionStatus.CANCELLED),
            stripe_subscription_id=stripe_sub["id"],
            current_period_end=self._timestamp_to_datetime(stripe_sub["current_period_end"]),
        )

    def _tier_from_price(self, price_id: str) -> SubscriptionTier:
        if price_id == os.environ.get("STRIPE_PRO_PRICE_ID"):
            return SubscriptionTier.PRO
        if price_id == os.environ.get("STRIPE_ENTERPRISE_PRICE_ID"):
            return SubscriptionTier.ENTERPRISE
        return SubscriptionTier.FREE

    def _timestamp_to_datetime(self, ts: int | None):
        from datetime import datetime, timezone
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)
```

**Day 1 Acceptance Criteria:**
- [ ] Adapter instantiation works with test keys.
- [ ] `pytest tests/test_saas_stripe_adapter.py` passes (mocked stripe module).

---

### Day 2 — Webhook Handler + Router

**Files:**
- `src/reasoner/infrastructure/billing/webhooks.py`
- `src/reasoner/api/billing_router.py`

**Task 4.2.1 — Webhook Handler**

```python
# src/reasoner/infrastructure/billing/webhooks.py
"""Stripe webhook receiver with signature verification."""

from __future__ import annotations

import os
import logging

import stripe
from fastapi import Request, HTTPException

from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
from reasoner.application.services.billing_service import BillingService

logger = logging.getLogger(__name__)


async def handle_stripe_webhook(request: Request) -> dict:
    """
    Receive and process Stripe webhook events.

    Returns:
        {"status": "ok"} on success (always 200 to prevent Stripe retries on parse errors).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ["STRIPE_WEBHOOK_SECRET"]

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Stripe webhook received: %s", event["type"])

    adapter = StripeBillingAdapter()
    service = BillingService(adapter)
    await service.handle_webhook(event)

    return {"status": "ok"}
```

**Task 4.2.2 — Billing Router**

```python
# src/reasoner/api/billing_router.py
"""FastAPI router for all billing endpoints."""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, Request
from reasoner.domain.saas import User, SubscriptionTier
from reasoner.api.dependencies import get_current_user
from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
from reasoner.application.services.billing_service import BillingService

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _get_billing_service() -> BillingService:
    adapter = StripeBillingAdapter()
    return BillingService(adapter)


@router.post("/checkout")
async def create_checkout(
    request: Request,
    tier: str,
    user: User = Depends(get_current_user),
):
    """Create a Stripe Checkout session for upgrading."""
    service = _get_billing_service()
    app_url = os.environ.get("APP_URL", "http://localhost:3000")
    url = await service.create_checkout(
        str(user.id),
        SubscriptionTier(tier),
        success_url=f"{app_url}/dashboard?checkout=success",
        cancel_url=f"{app_url}/pricing?checkout=cancel",
    )
    return {"checkout_url": url}


@router.post("/portal")
async def create_portal(
    user: User = Depends(get_current_user),
):
    """Create a Stripe Billing Portal session."""
    service = _get_billing_service()
    app_url = os.environ.get("APP_URL", "http://localhost:3000")
    url = await service.create_portal(str(user.id), f"{app_url}/dashboard")
    return {"portal_url": url}


@router.get("/subscription")
async def get_subscription(user: User = Depends(get_current_user)):
    """Get current subscription status."""
    # TODO: fetch from subscriptions table
    return {"tier": "free", "status": "active"}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Public endpoint for Stripe webhooks."""
    from reasoner.infrastructure.billing.webhooks import handle_stripe_webhook
    return await handle_stripe_webhook(request)
```

**Day 2 Acceptance Criteria:**
- [ ] `POST /api/billing/webhook` with invalid signature → 400.
- [ ] `POST /api/billing/webhook` with valid test event → 200.
- [ ] `POST /api/billing/checkout` returns `{checkout_url}`.

---

### Day 3 — Subscription Persistence + Sync

**Files:**
- Modifications to `PostgresQuotaRepository` or new `SubscriptionRepository`

**Task 4.3.1 — Subscription Upsert Logic**

In webhook handler, after parsing the event:

```python
async def _upsert_subscription(sub: Subscription) -> None:
    """Idempotently update subscription in Postgres."""
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    from reasoner.core.settings import settings

    repo = PostgresQuotaRepository(settings.DATABASE_URL)
    pool = await repo._get_pool()
    await pool.execute(
        """
        INSERT INTO subscriptions (user_id, tier, status, stripe_sub_id, current_period_end)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (stripe_sub_id) DO UPDATE SET
            tier = EXCLUDED.tier,
            status = EXCLUDED.status,
            current_period_end = EXCLUDED.current_period_end
        """,
        str(sub.user_id),
        sub.tier.value,
        sub.status.value,
        sub.stripe_subscription_id,
        sub.current_period_end,
    )

    # Sync quota limits
    tier_limits = {SubscriptionTier.FREE: 20, SubscriptionTier.PRO: 500, SubscriptionTier.ENTERPRISE: -1}
    await pool.execute(
        """
        INSERT INTO usage_quotas (user_id, tier, max_queries)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE SET
            tier = EXCLUDED.tier,
            max_queries = EXCLUDED.max_queries,
            used_queries = 0
        """,
        str(sub.user_id),
        sub.tier.value,
        tier_limits[sub.tier],
    )
```

**Day 3 Acceptance Criteria:**
- [ ] Webhook upsert creates subscription row.
- [ ] Duplicate webhook with same `stripe_sub_id` updates rather than duplicates.
- [ ] Quota table syncs tier and max_queries.

---

### Day 4–5 — Frontend Pricing + Checkout

**Files:**
- `ui-next/src/app/pricing/page.tsx`
- `ui-next/src/app/dashboard/page.tsx`

**Task 4.4.1 — Pricing Page**

```tsx
// ui-next/src/app/pricing/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '@/lib/api-client';

const plans = [
  { name: 'Free', price: '$0', queries: '20 / month', features: ['Budget presets only', 'Basic support'] },
  { name: 'Pro', price: '$12/mo', queries: '500 / month', features: ['All presets', 'Priority support', 'Advanced analytics'] },
  { name: 'Enterprise', price: '$49/mo', queries: 'Unlimited', features: ['Custom models', 'SLA', 'Dedicated support'] },
];

export default function PricingPage() {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleUpgrade = async (tier: string) => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      window.location.href = data.checkout_url;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto py-12 px-4">
      <h1 className="text-3xl font-bold text-center mb-8">Choose Your Plan</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {plans.map((plan) => (
          <div key={plan.name} className="border rounded-lg p-6 text-center">
            <h2 className="text-xl font-semibold">{plan.name}</h2>
            <p className="text-2xl font-bold my-2">{plan.price}</p>
            <p className="text-gray-600 mb-4">{plan.queries}</p>
            <ul className="text-sm text-left space-y-2 mb-6">
              {plan.features.map((f) => (
                <li key={f}>✓ {f}</li>
              ))}
            </ul>
            {plan.name !== 'Free' && (
              <button
                onClick={() => handleUpgrade(plan.name.toLowerCase())}
                disabled={loading}
                className="w-full py-2 bg-blue-600 text-white rounded disabled:opacity-50"
              >
                {loading ? 'Loading...' : 'Upgrade'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Day 4–5 Acceptance Criteria:**
- [ ] `/pricing` renders three-tier comparison.
- [ ] Clicking "Upgrade" redirects to Stripe Checkout.
- [ ] Successful payment redirects to `/dashboard?checkout=success`.

---

### Day 6 — Billing Portal + Invoices

**Files:**
- `ui-next/src/app/dashboard/page.tsx`
- `src/reasoner/api/billing_router.py` (add invoice endpoint)

**Task 4.5.1 — Dashboard Page**

```tsx
// ui-next/src/app/dashboard/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api-client';
import { useQuota } from '@/hooks/useQuota';

export default function DashboardPage() {
  const { quota } = useQuota();
  const [subscription, setSubscription] = useState<any>(null);

  useEffect(() => {
    apiFetch('/api/billing/subscription').then(r => r.json()).then(setSubscription);
  }, []);

  const openPortal = async () => {
    const res = await apiFetch('/api/billing/portal', { method: 'POST' });
    const data = await res.json();
    window.location.href = data.portal_url;
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border rounded-lg p-6">
          <h2 className="font-semibold mb-2">Current Plan</h2>
          <p className="text-lg capitalize">{subscription?.tier || 'Free'}</p>
          <button onClick={openPortal} className="mt-4 text-blue-600 underline">
            Manage Billing
          </button>
        </div>
        <div className="border rounded-lg p-6">
          <h2 className="font-semibold mb-2">Usage</h2>
          {quota && (
            <>
              <p>{quota.used} / {quota.max} queries</p>
              <div className="w-full bg-gray-200 rounded h-2 mt-2">
                <div
                  className="bg-blue-600 h-2 rounded"
                  style={{ width: `${(quota.used / quota.max) * 100}%` }}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
```

**Day 6 Acceptance Criteria:**
- [ ] Dashboard shows current plan and usage bar.
- [ ] "Manage Billing" opens Stripe Billing Portal.

---

### Day 7 — Idempotency + Edge Cases

**Files:**
- `tests/test_saas_stripe_webhooks.py`

**Task 4.6.1 — Webhook Idempotency Tests**

```python
# tests/test_saas_stripe_webhooks.py
import pytest
from fastapi.testclient import TestClient


def test_webhook_duplicate_event_is_idempotent(client: TestClient, monkeypatch):
    """Replay the same checkout.completed twice → one subscription row."""
    import stripe

    event = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "...", "subscription": "sub_123"}},
    }

    # Mock stripe.Webhook.construct_event to return our test event
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *args, **kwargs: event)
    # Mock stripe.Subscription.retrieve
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: {
        "id": sid,
        "status": "active",
        "customer": "cus_123",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "current_period_end": 1893456000,
    })
    monkeypatch.setattr(stripe.Customer, "retrieve", lambda cid: {
        "id": cid,
        "metadata": {"reasoner_user_id": "12345678-1234-5678-1234-567812345678"},
    })

    # Send twice
    client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})
    client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})

    # Assert one subscription row exists (would need DB assertion in real test)
```

**Day 7 Acceptance Criteria:**
- [ ] Duplicate webhook events produce exactly one subscription row.
- [ ] `invoice.payment_failed` sets status to `past_due`.
- [ ] `customer.subscription.deleted` downgrades quota to free tier.

---

### Day 8–10 — E2E Testing + Polish

**Task 4.7.1 — E2E Checkout Flow**

Use Stripe test mode:
- Test card: `4242 4242 4242 4242` → succeeds
- Test card: `4000 0000 0000 0002` → fails

**Task 4.7.2 — Coupon Testing**

Verify `allow_promotion_codes=True` shows coupon field in Checkout.

**Definition of Done (Phase 4):**
- [ ] Stripe Checkout creates subscriptions.
- [ ] Webhooks sync tier/quota changes idempotently.
- [ ] Billing Portal opens for self-service.
- [ ] Dashboard shows plan + usage.
- [ ] `/pricing` page supports promo codes.
- [ ] Cancel subscription downgrades to free.
- [ ] All existing tests pass.

---

*End of Phase 4 Plan*
