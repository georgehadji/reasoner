"""Billing Service — Orchestrates checkout, portal, and webhook sync."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from datetime import UTC, datetime

from reasoner.application.ports.billing_port import BillingPort
from reasoner.application.services.credit_service import CreditService
from reasoner.domain.credits import CreditReason
from reasoner.domain.saas import SubscriptionTier, UnresolvedBillingOwnerError

logger = logging.getLogger(__name__)

# Injected at API startup (api/__init__.py): application code may not import api/,
# and the credit service's repository choice lives there.
_credit_service_provider: Callable[[], CreditService] | None = None


def set_credit_service_provider(provider: Callable[[], CreditService] | None) -> None:
    global _credit_service_provider
    _credit_service_provider = provider


async def _paypal_activate(sub, repo, event_at, obj=None) -> None:
    # ACTIVATED and RE-ACTIVATED (a payment after a failure) both end active.
    if await repo.upsert_subscription(sub, event_at):
        await repo.sync_quota_for_subscription(sub)
    logger.info(
        "PayPal subscription synced for user %s: tier=%s status=%s",
        sub.user_id, sub.tier.value, sub.status.value
    )


async def _paypal_cancel(sub, repo, event_at, obj=None) -> None:
    # CANCELLED and EXPIRED (the paid term ran out) both end cancelled.
    if not sub.paypal_subscription_id:
        return
    if await repo.set_subscription_status_by_paypal(
        sub.paypal_subscription_id, "cancelled", event_at,
    ):
        await repo.sync_quota_for_subscription(sub)
    else:
        # No row yet (cancel overtook ACTIVATED) or a newer event holds it; the
        # repo inserts a cancelled marker only in the first case.
        await repo.record_paypal_cancel_tombstone(sub, event_at)


async def _paypal_past_due(sub, repo, event_at, obj=None) -> None:
    if sub.paypal_subscription_id:
        await repo.set_subscription_status_by_paypal(
            sub.paypal_subscription_id, "past_due", event_at,
        )


async def _paypal_payment_completed(sub, repo, event_at, obj=None) -> None:
    # A successful retry (PAYMENT.SALE.COMPLETED) lifts a past_due subscription.
    # The event names only the subscription, so the repo returns the stored row.
    if not sub.paypal_subscription_id:
        return
    revived = await repo.reactivate_past_due_by_paypal(sub.paypal_subscription_id, event_at)
    if revived is not None:
        from reasoner.infrastructure.persistence.cached_subscription_repo import (
            invalidate_subscription,
        )

        await repo.sync_quota_for_subscription(revived)
        await invalidate_subscription(str(revived.user_id))


async def _paypal_refund(sub, repo, event_at, obj=None) -> None:
    # The refund event names the subscription at best; the owner comes from our table.
    paypal_id = sub.paypal_subscription_id
    user_id = await repo.get_user_by_paypal_sub_id(paypal_id) if paypal_id else None
    if user_id is None:
        raise UnresolvedBillingOwnerError("PayPal refund names no known subscription")
    obj = obj or {}
    amount = obj.get("amount") or {}
    try:
        cents = round(abs(float(amount.get("total") or 0)) * 100)
    except (TypeError, ValueError):
        cents = 0
    await claw_back_credits(
        user_id,
        f"refund:{obj.get('id')}",
        cents,
        amount.get("currency_code") or amount.get("currency"),
        "PAYMENT.SALE refund",
    )


async def claw_back_credits(user_id: str, key: str, cents: int, currency, label: str) -> None:
    """Debit the credits a refunded or disputed payment bought, idempotent on ``key``."""
    if _credit_service_provider is None:
        logger.error("No credit service wired; %s (user %s) not clawed back", key, user_id)
    elif currency and str(currency).lower() != "usd":
        # Credits are USD; a cents/100 debit of another currency would mis-charge.
        logger.warning("%s (user %s) is in %s, not clawed back", key, user_id, currency)
    elif cents and cents > 0:
        await _credit_service_provider().charge_usd(
            user_id,
            cost_usd=cents / 100,
            reference_id=key,
            reason=CreditReason.ADMIN_ADJUSTMENT,
            description=f"Chargeback adjustment ({label})",
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
    "PAYMENT.SALE.COMPLETED": _paypal_payment_completed,
    "PAYMENT.SALE.REFUNDED": _paypal_refund,
    "PAYMENT.SALE.REVERSED": _paypal_refund,
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
        )

        event_type = event.get("type", "")
        # PayPal events use "event_type" key
        if not event_type:
            event_type = event.get("event_type", "")

        try:
            await self._apply_webhook(
                event_type,
                sub,
                repo,
                event_time(event),
                (event.get("data") or {}).get("object") or event.get("resource"),
            )
        finally:
            # Invalidate even on failure: a partial write may have landed, so
            # the cached subscription can no longer be trusted.
            await invalidate_subscription(str(sub.user_id))

    async def _apply_webhook(
        self, event_type: str, sub, repo, event_at=None, payload: dict | None = None
    ) -> None:
        """Route a webhook event to the matching persistence action.

        Every write carries the event's own time and is skipped when the row
        already holds a newer event, so retries and dead-letter replays apply
        in any order (BIL-15). A skipped write skips its quota sync too.
        """
        # --- PayPal events ---
        if event_type.startswith(("BILLING.SUBSCRIPTION.", "PAYMENT.SALE.")):
            handler = PAYPAL_HANDLERS.get(event_type)
            if handler is None:
                logger.debug("Unhandled PayPal event type: %s", event_type)
                return
            await handler(sub, repo, event_at, payload)
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

        if event_type in ("charge.refunded", "charge.dispute.created"):
            await self._claw_back(event_type, sub, repo, event_at, payload or {})
            return

        if event_type == "invoice.payment_failed":
            if sub.stripe_subscription_id:
                await repo.set_subscription_status(
                    sub.stripe_subscription_id,
                    "past_due",
                    event_at,
                )
            return

        # invoice.payment_succeeded is deliberately unhandled: the adapter gives it no
        # subscription id, and renewal arrives as customer.subscription.updated.
        if event_type in ("checkout.session.completed", "customer.subscription.updated"):
            # Serialized per user: two concurrent checkouts otherwise both pass
            # the duplicate check and both get stored live.
            lock = getattr(repo, "user_lock", None)
            async with lock(str(sub.user_id)) if lock else nullcontext():
                if await self._is_duplicate_live(sub, repo):
                    return
                # Upsert subscription and sync quota
                if await repo.upsert_subscription(sub, event_at):
                    await repo.sync_quota_for_subscription(sub)
            logger.info(
                "Stripe subscription synced for user %s: tier=%s status=%s",
                sub.user_id, sub.tier.value, sub.status.value
            )
            return

        logger.debug("Unhandled event type: %s", event_type)

    async def _claw_back(self, event_type: str, sub, repo, event_at, obj: dict) -> None:
        """A refund or dispute takes back the credits the money bought.

        The ledger row is keyed ``dispute:<id>`` / ``refund:<charge id>`` so a
        replayed event moves nothing twice, and overdraws: the credits may
        already be spent. A dispute, or a charge refunded in full, also puts the
        subscription past_due. shortcut: a second partial refund on one charge
        reuses the key and is not clawed back; key on the refund id if that matters.
        """
        is_dispute = event_type == "charge.dispute.created"
        cents = obj.get("amount") if is_dispute else obj.get("amount_refunded")
        key = f"{'dispute' if is_dispute else 'refund'}:{obj.get('id')}"
        await claw_back_credits(str(sub.user_id), key, cents, obj.get("currency"), event_type)
        if is_dispute or obj.get("refunded"):
            existing = await repo.get_subscription_by_user(str(sub.user_id))
            if existing is not None and existing.stripe_subscription_id:
                await repo.set_subscription_status(
                    existing.stripe_subscription_id, "past_due", event_at
                )

    async def _is_duplicate_live(self, sub, repo) -> bool:
        """A second checkout completed while another subscription is live.

        Both were billed; the new one is cancelled at the provider and never
        stored as live, so the user keeps one tracked subscription (BIL-14).
        """
        from reasoner.domain.saas import LIVE_STATUSES

        existing = await repo.get_subscription_by_user(str(sub.user_id))
        if (
            existing is None
            or existing.status not in LIVE_STATUSES
            or existing.tier == SubscriptionTier.FREE
            or not existing.stripe_subscription_id
            or existing.stripe_subscription_id == sub.stripe_subscription_id
        ):
            return False
        logger.warning(
            "User %s already has live subscription %s; cancelling duplicate %s",
            sub.user_id, existing.stripe_subscription_id, sub.stripe_subscription_id,
        )
        await self._port.cancel_subscription(sub.stripe_subscription_id)
        # Both were billed. The refund is idempotent per subscription, so a
        # retried or replayed event cannot refund twice.
        await self._port.refund_latest_charge(sub.stripe_subscription_id)
        return True


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
