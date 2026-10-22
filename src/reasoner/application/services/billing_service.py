"""Billing Service — Orchestrates checkout, portal, and webhook sync."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from reasoner.application.ports.billing_port import BillingPort
from reasoner.domain.saas import SubscriptionTier

logger = logging.getLogger(__name__)


async def _paypal_activate(sub, repo, event_at) -> None:
    # ACTIVATED and RE-ACTIVATED (a payment after a failure) both end active.
    if await repo.upsert_subscription(sub, event_at):
        await repo.sync_quota_for_subscription(sub)
    logger.info(
        "PayPal subscription synced for user %s: tier=%s status=%s",
        sub.user_id, sub.tier.value, sub.status.value
    )


async def _paypal_cancel(sub, repo, event_at) -> None:
    # CANCELLED and EXPIRED (the paid term ran out) both end cancelled.
    if sub.paypal_subscription_id and await repo.set_subscription_status_by_paypal(
        sub.paypal_subscription_id, "cancelled", event_at,
    ):
        await repo.sync_quota_for_subscription(sub)


async def _paypal_past_due(sub, repo, event_at) -> None:
    if sub.paypal_subscription_id:
        await repo.set_subscription_status_by_paypal(
            sub.paypal_subscription_id, "past_due", event_at,
        )


# One row per PayPal lifecycle event. paypal_adapter.PAYPAL_EVENT_STATUS holds
# the matching event -> status table; tests/test_paypal_events.py pins that the
# two have the same keys. Each handler is wrapped by the monotonic event guard
# inside the repository write (BIL-15).
PAYPAL_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {
    "BILLING.SUBSCRIPTION.ACTIVATED": _paypal_activate,
    "BILLING.SUBSCRIPTION.RE-ACTIVATED": _paypal_activate,
    "BILLING.SUBSCRIPTION.CANCELLED": _paypal_cancel,
    "BILLING.SUBSCRIPTION.EXPIRED": _paypal_cancel,
    "BILLING.SUBSCRIPTION.SUSPENDED": _paypal_past_due,
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED": _paypal_past_due,
}


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
            await self._apply_webhook(event_type, sub, repo, event_time(event))
        finally:
            # Invalidate even on failure: a partial write may have landed, so
            # the cached subscription can no longer be trusted.
            await invalidate_subscription(str(sub.user_id))

    async def _apply_webhook(self, event_type: str, sub, repo, event_at=None) -> None:
        """Route a webhook event to the matching persistence action.

        Every write carries the event's own time and is skipped when the row
        already holds a newer event, so retries and dead-letter replays apply
        in any order (BIL-15). A skipped write skips its quota sync too.
        """
        # --- PayPal events ---
        if event_type.startswith("BILLING.SUBSCRIPTION."):
            handler = PAYPAL_HANDLERS.get(event_type)
            if handler is None:
                logger.debug("Unhandled PayPal event type: %s", event_type)
                return
            await handler(sub, repo, event_at)
            return

        # --- Stripe events ---
        if event_type == "customer.subscription.deleted":
            # Downgrade to free — update subscription status
            if sub.stripe_subscription_id:
                if await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "cancelled",
                    event_at,
                ):
                    await repo.sync_quota_for_subscription(sub)
            return

        if event_type == "invoice.payment_failed":
            if sub.stripe_subscription_id:
                await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "past_due",
                    event_at,
                )
            return

        if event_type == "invoice.payment_succeeded":
            # Payment succeeded — ensure subscription is active and reset usage for the new period
            if sub.stripe_subscription_id:
                if await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "active",
                    event_at,
                ):
                    await repo.sync_quota_for_subscription(sub)
            return

        if event_type in ("checkout.session.completed", "customer.subscription.updated"):
            # Upsert subscription and sync quota
            if await repo.upsert_subscription(sub, event_at):
                await repo.sync_quota_for_subscription(sub)
            logger.info(
                "Stripe subscription synced for user %s: tier=%s status=%s",
                sub.user_id, sub.tier.value, sub.status.value
            )
            return

        logger.debug("Unhandled event type: %s", event_type)


def event_time(event: dict) -> datetime | None:
    """When the provider says the event happened: Stripe ``created`` (epoch
    seconds), PayPal ``create_time`` (ISO-8601). None when absent or unreadable,
    which applies the write unconditionally, as before."""
    created = event.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool):
        return datetime.fromtimestamp(created, tz=UTC)
    stamp = event.get("create_time")
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
