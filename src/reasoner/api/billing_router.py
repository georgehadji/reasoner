"""FastAPI router for all billing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from reasoner.api.dependencies import get_current_user, require_key_scope
from reasoner.application.services.billing_service import BillingService
from reasoner.core.settings import settings
from reasoner.domain.saas import SubscriptionTier, User
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _get_stripe_service() -> BillingService:
    adapter = StripeBillingAdapter()
    return BillingService(adapter)


def _get_paypal_service() -> BillingService:
    adapter = PayPalBillingAdapter()
    return BillingService(adapter)


@router.post("/checkout")
async def create_checkout(
    request: Request,
    tier: str,
    provider: str = "stripe",
    user: User = Depends(require_key_scope("write")),
):
    """Create a checkout session for upgrading.

    provider: "stripe" (default) or "paypal"
    """
    try:
        tier_enum = SubscriptionTier(tier.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}. Must be one of: free, pro, enterprise.") from exc

    app_url = settings.APP_URL

    # One live subscription per user (BIL-14). A paying user changes plan in the
    # Stripe portal, which prorates (Q4), instead of buying a second plan.
    from reasoner.domain.saas import CheckoutDecision, checkout_allowed
    from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

    existing = await PostgresSubscriptionRepository(
        settings.DATABASE_URL.replace("+asyncpg", ""), pool_size=10,
    ).get_subscription_by_user(str(user.id))
    decision = checkout_allowed(existing, tier_enum)
    if decision is not CheckoutDecision.ALLOW:
        portal_url = None
        if existing is not None and existing.stripe_customer_id:
            portal_url = await _get_stripe_service().create_portal(
                str(user.id), f"{app_url}/dashboard"
            )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "You already have an active subscription.",
                "decision": decision.value,
                "portal_url": portal_url,
            },
        )

    success_url = f"{app_url}/dashboard?checkout=success&provider={provider}"
    cancel_url = f"{app_url}/pricing?checkout=cancel&provider={provider}"

    if provider.lower() == "paypal":
        service = _get_paypal_service()
    else:
        service = _get_stripe_service()

    try:
        url = await service.create_checkout(
            str(user.id),
            tier_enum,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Checkout creation failed: {exc}") from exc

    return {"checkout_url": url, "provider": provider}


@router.post("/portal")
async def create_portal(
    user: User = Depends(require_key_scope("write")),
):
    """Create a Stripe Billing Portal session."""
    service = _get_stripe_service()
    app_url = settings.APP_URL
    url = await service.create_portal(str(user.id), f"{app_url}/dashboard")
    return {"portal_url": url}


@router.get("/subscription")
async def get_subscription(user: User = Depends(get_current_user)):
    """Get current subscription status from database."""
    from reasoner.core.settings import settings
    from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

    repo = PostgresSubscriptionRepository(
        settings.DATABASE_URL.replace("+asyncpg", ""),
        pool_size=10,
    )
    sub = await repo.get_subscription_by_user(str(user.id))
    if sub is None:
        return {"tier": "free", "status": "active"}
    return {
        "tier": sub.tier.value,
        "status": sub.status.value,
        "stripe_subscription_id": sub.stripe_subscription_id,
        "paypal_subscription_id": getattr(sub, "paypal_subscription_id", None),
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Public endpoint for Stripe webhooks."""
    from reasoner.infrastructure.billing.webhooks import handle_stripe_webhook
    return await handle_stripe_webhook(request)


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request):
    """Public endpoint for PayPal webhooks."""
    from reasoner.infrastructure.billing.webhooks import handle_paypal_webhook
    return await handle_paypal_webhook(request)
