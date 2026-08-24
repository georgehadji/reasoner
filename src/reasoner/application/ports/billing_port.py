"""
Billing Port — Abstract interface for payment providers.

Stripe is the default adapter, but the domain never imports stripe.
"""

from __future__ import annotations

from typing import Any, Protocol

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

    async def sync_subscription(self, provider_event: dict[str, Any]) -> Subscription:
        """
        Idempotently sync a subscription from a provider webhook event.

        Args:
            provider_event: Raw event payload (e.g., Stripe webhook JSON).

        Returns:
            Canonical Subscription entity reflecting the latest state.
        """
        ...

    async def cancel_subscription(self, stripe_subscription_id: str) -> None:
        """Immediately cancel a subscription at the provider."""
        ...
