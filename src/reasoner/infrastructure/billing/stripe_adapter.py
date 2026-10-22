"""Stripe implementation of BillingPort."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC
from uuid import UUID, uuid4

import stripe

from reasoner.application.ports.billing_port import BillingPort
from reasoner.domain.saas import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    UnresolvedBillingOwnerError,
)

logger = logging.getLogger(__name__)


def to_plain(obj):
    """A StripeObject as a plain dict; anything else passes through unchanged.

    StripeObject stopped inheriting from dict in stripe-python 15, so `.get()`
    and `dict(obj)` raise on what the SDK returns. Each SDK result is converted
    once, where it enters this module, and the rest works on plain dicts.
    """
    return obj.to_dict() if isinstance(obj, stripe.StripeObject) else obj


class StripeBillingAdapter(BillingPort):
    def __init__(self, api_key: str | None = None):
        stripe.api_key = api_key or os.environ.get("STRIPE_SECRET_KEY", "")

    async def create_checkout_session(
        self,
        user_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        price_id = self._price_id_for_tier(tier)
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            # stripe-python 16 removed payment_method_types; this filters the
            # dynamically eligible methods down to the same two.
            allowed_payment_method_types=["card", "link"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,
            # The webhook resolvers read this; nothing used to write it, so every
            # renewal and plan change failed to find its user (BIL-13).
            metadata={"reasoner_user_id": user_id},
            subscription_data={"metadata": {"reasoner_user_id": user_id}},
            allow_promotion_codes=True,
            automatic_tax={"enabled": True},
            billing_address_collection="required",
            payment_method_options={
                "card": {
                    "setup_future_usage": "off_session",
                },
            },
        )
        return session.url

    async def create_portal_session(self, user_id: str, return_url: str) -> str:
        # The customer id stored with the subscription. The old lookup paged
        # through every Stripe customer for a metadata value nothing ever set,
        # so the portal always failed (BIL-13).
        sub = await _subscription_repo().get_subscription_by_user(user_id)
        if sub is None or not sub.stripe_customer_id:
            raise ValueError(f"No Stripe customer found for user {user_id}")

        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=sub.stripe_customer_id,
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
        elif event_type == "invoice.payment_failed":
            return await self._handle_payment_failed(data)

        # Return a no-op subscription for unhandled events
        return Subscription(
            id=uuid4(),
            user_id=uuid4(),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.CANCELLED,
        )

    def _price_id_for_tier(self, tier: SubscriptionTier) -> str:
        if tier == SubscriptionTier.FREE:
            return ""
        mapping = {
            SubscriptionTier.PRO: os.environ.get("STRIPE_PRO_PRICE_ID", ""),
            SubscriptionTier.ENTERPRISE: os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
        }
        return mapping.get(tier, "")

    async def _handle_checkout_completed(self, session: dict) -> Subscription:
        # Extract user_id from client_reference_id
        user_id = session.get("client_reference_id")
        if not user_id:
            raise ValueError("Missing client_reference_id in checkout session")
        # Subscription object is in subscription field
        sub_id = session.get("subscription")
        stripe_sub = to_plain(await asyncio.to_thread(stripe.Subscription.retrieve, sub_id))
        if customer := session.get("customer"):
            await asyncio.to_thread(
                stripe.Customer.modify, customer, metadata={"reasoner_user_id": user_id}
            )
        return self._stripe_sub_to_domain(stripe_sub, UUID(user_id))

    async def _resolve_user_id(self, stripe_sub: dict) -> UUID:
        """Our user for a Stripe subscription (the anti-corruption layer).

        Customer metadata first, then the subscription's own metadata, then our
        subscriptions table. A database error propagates, so the webhook is
        retried; only a clean "nobody" raises UnresolvedBillingOwnerError (BIL-13).
        """
        customer_id = stripe_sub.get("customer")
        if customer_id:
            customer = to_plain(await asyncio.to_thread(stripe.Customer.retrieve, customer_id))
            if found := (customer.get("metadata") or {}).get("reasoner_user_id"):
                return UUID(found)
        if found := (stripe_sub.get("metadata") or {}).get("reasoner_user_id"):
            return UUID(found)
        if stripe_sub.get("id") and (
            found := await _subscription_repo().get_user_by_stripe_sub_id(stripe_sub["id"])
        ):
            return UUID(found)
        raise UnresolvedBillingOwnerError(
            f"Stripe subscription {stripe_sub.get('id')} (customer {customer_id}) has no known user"
        )

    async def _handle_subscription_updated(self, stripe_sub: dict) -> Subscription:
        # Apply the live state, not the payload snapshot: a retried or replayed
        # event then cannot reinstate a state the subscription has left, even
        # when two events share a timestamp (BIL-15).
        if stripe_sub.get("id"):
            stripe_sub = to_plain(
                await asyncio.to_thread(stripe.Subscription.retrieve, stripe_sub["id"])
            )
        return self._stripe_sub_to_domain(stripe_sub, await self._resolve_user_id(stripe_sub))

    async def _handle_subscription_deleted(self, stripe_sub: dict) -> Subscription:
        return Subscription(
            id=uuid4(),
            user_id=await self._resolve_user_id(stripe_sub),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.CANCELLED,
            stripe_subscription_id=stripe_sub["id"],
            stripe_customer_id=stripe_sub.get("customer"),
        )

    def _stripe_sub_to_domain(self, stripe_sub: dict, user_id: UUID) -> Subscription:
        sub_dict = to_plain(stripe_sub)
        items = sub_dict.get("items", {}).get("data", []) if isinstance(sub_dict.get("items"), dict) else []
        price_id = items[0]["price"]["id"] if items else None
        # API 2025-03-31 moved current_period_end onto the subscription item.
        # Webhook payloads follow the endpoint's API version, so read either.
        period_end = (items[0].get("current_period_end") if items else None) or sub_dict.get(
            "current_period_end"
        )
        tier = self._tier_from_price(price_id) if price_id else SubscriptionTier.FREE
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELLED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
        }
        return Subscription(
            id=uuid4(),
            user_id=user_id,
            tier=tier,
            status=status_map.get(sub_dict.get("status"), SubscriptionStatus.CANCELLED),
            stripe_subscription_id=sub_dict.get("id"),
            stripe_customer_id=sub_dict.get("customer"),
            current_period_end=self._timestamp_to_datetime(period_end),
        )

    def _tier_from_price(self, price_id: str) -> SubscriptionTier:
        if price_id == os.environ.get("STRIPE_PRO_PRICE_ID"):
            return SubscriptionTier.PRO
        if price_id == os.environ.get("STRIPE_ENTERPRISE_PRICE_ID"):
            return SubscriptionTier.ENTERPRISE
        return SubscriptionTier.FREE

    async def cancel_subscription(self, stripe_subscription_id: str) -> None:
        """Immediately cancel a Stripe subscription. Already gone counts as done.

        Stripe rejects cancelling a cancelled subscription, so account deletion
        returned 502 forever for a subscription cancelled at Stripe but still
        live locally (docs/plans/audit-remediation-2-2026-10-20.md BIL-19).
        """
        try:
            current = to_plain(
                await asyncio.to_thread(stripe.Subscription.retrieve, stripe_subscription_id)
            )
            if current.get("status") in ("canceled", "incomplete_expired"):
                return
            await asyncio.to_thread(stripe.Subscription.cancel, stripe_subscription_id)
        except stripe.InvalidRequestError as exc:
            if getattr(exc, "code", None) == "resource_missing":
                return
            raise

    async def _handle_payment_failed(self, invoice: dict) -> Subscription:
        # API 2025-03-31 moved the invoice's subscription under
        # parent.subscription_details; older endpoint versions send it top-level.
        details = (invoice.get("parent") or {}).get("subscription_details") or {}
        subscription_id = details.get("subscription") or invoice.get("subscription")
        if not subscription_id:
            # No subscription linked — return no-op
            return Subscription(
                id=uuid4(),
                user_id=uuid4(),
                tier=SubscriptionTier.FREE,
                status=SubscriptionStatus.CANCELLED,
            )
        stripe_sub = to_plain(
            await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
        )
        return Subscription(
            id=uuid4(),
            user_id=await self._resolve_user_id(stripe_sub),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.PAST_DUE,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=stripe_sub.get("customer"),
        )

    def _timestamp_to_datetime(self, ts: int | None):
        from datetime import datetime
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)


def _subscription_repo():
    from reasoner.core.settings import settings
    from reasoner.infrastructure.persistence.subscription_repo import (
        PostgresSubscriptionRepository,
    )

    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    return PostgresSubscriptionRepository(dsn, pool_size=10)
