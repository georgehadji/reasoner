"""Billing Service — Orchestrates checkout, portal, and webhook sync."""

from __future__ import annotations

import logging

from reasoner.application.ports.billing_port import BillingPort
from reasoner.domain.saas import SubscriptionTier

logger = logging.getLogger(__name__)


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
        """Idempotent webhook processing with subscription persistence.

        Handles both Stripe and PayPal webhook events.
        """
        sub = await self._port.sync_subscription(event)

        # Persist to database
        from reasoner.core.settings import settings
        from reasoner.infrastructure.persistence.cached_subscription_repo import (
            invalidate_subscription,
        )
        from reasoner.infrastructure.persistence.subscription_repo import (
            PostgresSubscriptionRepository,
        )

        repo = PostgresSubscriptionRepository(
            settings.DATABASE_URL.replace("+asyncpg", ""),
            pool_size=10,
        )

        event_type = event.get("type", "")
        # PayPal events use "event_type" key
        if not event_type:
            event_type = event.get("event_type", "")

        try:
            await self._apply_webhook(event_type, sub, repo)
        finally:
            # Invalidate even on failure: a partial write may have landed, so
            # the cached subscription can no longer be trusted.
            await invalidate_subscription(str(sub.user_id))

    async def _apply_webhook(self, event_type: str, sub, repo) -> None:
        """Route a webhook event to the matching persistence action."""
        # --- PayPal events ---
        if event_type.startswith("BILLING.SUBSCRIPTION."):
            if event_type == "BILLING.SUBSCRIPTION.CANCELLED":
                if sub.paypal_subscription_id:
                    await repo.set_subscription_status_by_paypal(
                        sub.paypal_subscription_id,
                        "cancelled",
                    )
                    await repo.sync_quota_for_subscription(sub)
                return

            if event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
                if sub.paypal_subscription_id:
                    await repo.set_subscription_status_by_paypal(
                        sub.paypal_subscription_id,
                        "past_due",
                    )
                return

            if event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
                if sub.paypal_subscription_id:
                    await repo.set_subscription_status_by_paypal(
                        sub.paypal_subscription_id,
                        "past_due",
                    )
                return

            if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
                await repo.upsert_subscription(sub)
                await repo.sync_quota_for_subscription(sub)
                logger.info(
                    "PayPal subscription synced for user %s: tier=%s status=%s",
                    sub.user_id, sub.tier.value, sub.status.value
                )
                return

            logger.debug("Unhandled PayPal event type: %s", event_type)
            return

        # --- Stripe events ---
        if event_type == "customer.subscription.deleted":
            # Downgrade to free — update subscription status
            if sub.stripe_subscription_id:
                await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "cancelled",
                )
                await repo.sync_quota_for_subscription(sub)
            return

        if event_type == "invoice.payment_failed":
            if sub.stripe_subscription_id:
                await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "past_due",
                )
            return

        if event_type == "invoice.payment_succeeded":
            # Payment succeeded — ensure subscription is active and reset usage for the new period
            if sub.stripe_subscription_id:
                await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "active",
                )
                await repo.sync_quota_for_subscription(sub)
            return

        if event_type in ("checkout.session.completed", "customer.subscription.updated"):
            # Upsert subscription and sync quota
            await repo.upsert_subscription(sub)
            await repo.sync_quota_for_subscription(sub)
            logger.info(
                "Stripe subscription synced for user %s: tier=%s status=%s",
                sub.user_id, sub.tier.value, sub.status.value
            )
            return

        logger.debug("Unhandled event type: %s", event_type)
