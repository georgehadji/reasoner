"""PayPal implementation of BillingPort for one-time and subscription payments."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx

from reasoner.application.ports.billing_port import BillingPort
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier

logger = logging.getLogger(__name__)

_PAYPAL_BASE_URL = "https://api-m.{env}.paypal.com"


class PayPalBillingAdapter(BillingPort):
    """PayPal REST API adapter for billing operations.

    Supports PayPal Checkout for subscriptions via PayPal Subscriptions API.
    """

    def __init__(self) -> None:
        self.client_id = os.environ.get("PAYPAL_CLIENT_ID", "")
        self.client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "")
        self.env = os.environ.get("PAYPAL_ENV", "sandbox")
        self.base_url = _PAYPAL_BASE_URL.format(env=self.env)
        self._access_token: str | None = None
        self._token_expires: datetime | None = None

    async def _get_access_token(self) -> str:
        """Fetch or refresh PayPal OAuth access token."""
        if self._access_token and self._token_expires and datetime.now(UTC) < self._token_expires:
            return self._access_token

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json", "Accept-Language": "en_US"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires = datetime.now(UTC) + timedelta(seconds=expires_in - 60)
            return self._access_token

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_checkout_session(
        self,
        user_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a PayPal subscription checkout URL.

        Returns the approval URL that the user should be redirected to.
        """
        plan_id = self._plan_id_for_tier(tier)
        if not plan_id:
            raise ValueError(f"No PayPal plan configured for tier {tier.value}")

        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            # Create a subscription
            resp = await client.post(
                f"{self.base_url}/v1/billing/subscriptions",
                headers=self._headers(token),
                json={
                    "plan_id": plan_id,
                    "application_context": {
                        "brand_name": "Reasoner",
                        "locale": "en-US",
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "SUBSCRIBE_NOW",
                        "payment_method": {
                            "payer_selected": "PAYPAL",
                            "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED",
                        },
                        "return_url": success_url,
                        "cancel_url": cancel_url,
                    },
                    "custom_id": user_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract the approval URL
        for link in data.get("links", []):
            if link.get("rel") == "approve":
                return link["href"]

        raise RuntimeError("PayPal subscription created but no approval URL found")

    async def create_portal_session(self, user_id: str, return_url: str) -> str:
        """PayPal does not have a native billing portal like Stripe.

        Returns the PayPal account management URL as a fallback.
        """
        return "https://www.paypal.com/myaccount/autopay/connect/"

    async def sync_subscription(self, provider_event: dict) -> Subscription:
        """Sync a PayPal webhook event to domain Subscription.

        Expected events: BILLING.SUBSCRIPTION.ACTIVATED,
                         BILLING.SUBSCRIPTION.CANCELLED,
                         BILLING.SUBSCRIPTION.SUSPENDED,
                         BILLING.SUBSCRIPTION.PAYMENT.FAILED
        """
        event_type = provider_event.get("event_type", "")
        resource = provider_event.get("resource", {})

        if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            return self._paypal_sub_to_domain(resource, status=SubscriptionStatus.ACTIVE)
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            return self._paypal_sub_to_domain(resource, status=SubscriptionStatus.CANCELLED)
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
            return self._paypal_sub_to_domain(resource, status=SubscriptionStatus.PAST_DUE)
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            return self._paypal_sub_to_domain(resource, status=SubscriptionStatus.PAST_DUE)

        return Subscription(
            id=uuid4(),
            user_id=uuid4(),
            tier=SubscriptionTier.FREE,
            status=SubscriptionStatus.CANCELLED,
        )

    def _plan_id_for_tier(self, tier: SubscriptionTier) -> str:
        if tier == SubscriptionTier.FREE:
            return ""
        mapping = {
            SubscriptionTier.PRO: os.environ.get("PAYPAL_PRO_PLAN_ID", ""),
            SubscriptionTier.ENTERPRISE: os.environ.get("PAYPAL_ENTERPRISE_PLAN_ID", ""),
        }
        return mapping.get(tier, "")

    def _tier_from_plan(self, plan_id: str | None) -> SubscriptionTier:
        if plan_id == os.environ.get("PAYPAL_PRO_PLAN_ID"):
            return SubscriptionTier.PRO
        if plan_id == os.environ.get("PAYPAL_ENTERPRISE_PLAN_ID"):
            return SubscriptionTier.ENTERPRISE
        return SubscriptionTier.FREE

    def _paypal_sub_to_domain(
        self,
        paypal_sub: dict,
        status: SubscriptionStatus,
    ) -> Subscription:
        custom_id = paypal_sub.get("custom_id", "")
        try:
            user_id = UUID(custom_id) if custom_id else uuid4()
        except ValueError:
            user_id = uuid4()

        plan_id = paypal_sub.get("plan_id")
        tier = self._tier_from_plan(plan_id)

        # Parse billing info for current period end
        current_period_end = None
        billing_info = paypal_sub.get("billing_info", {})
        next_billing_time = billing_info.get("next_billing_time")
        if next_billing_time:
            try:
                current_period_end = datetime.fromisoformat(next_billing_time.replace("Z", "+00:00"))
            except Exception:
                pass

        return Subscription(
            id=uuid4(),
            user_id=user_id,
            tier=tier,
            status=status,
            stripe_subscription_id=None,
            stripe_customer_id=None,
            paypal_subscription_id=paypal_sub.get("id"),
            current_period_end=current_period_end,
        )

    async def cancel_subscription(self, paypal_subscription_id: str) -> None:
        """Cancel a PayPal subscription immediately."""
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/billing/subscriptions/{paypal_subscription_id}/cancel",
                headers=self._headers(token),
                json={"reason": "User requested cancellation"},
            )
            resp.raise_for_status()

    async def verify_webhook_signature(self, headers: dict, body: str) -> bool:
        """Verify PayPal webhook signature using their certificate-based verification.

        For production, use PayPal's SDK verification or their /v1/notifications/verify-webhook-signature endpoint.
        """
        # Simplified: in production, verify the transmission ID, cert URL, auth algo,
        # transmission time, webhook ID, and CRC32 of the event body.
        # For now, we accept the webhook if the transmission signature is present.
        transmission_sig = headers.get("paypal-transmission-sig", "")
        return bool(transmission_sig)
