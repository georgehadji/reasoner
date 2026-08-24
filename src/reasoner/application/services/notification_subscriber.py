"""
Notification Subscriber — EventBus subscriber for transactional email alerts.

Sends email notifications for critical SaaS events:
- Webhook processing failures (billing integration health)
- Spend cap exceeded (cost management)
- Payment failures
- Subscription changes
"""

from __future__ import annotations

import logging

from reasoner.application.ports.email_port import EmailMessage
from reasoner.core.events.domain_events import (
    DomainEvent,
    PipelineEventType,
    SaaSEventType,
)

logger = logging.getLogger(__name__)


class NotificationSubscriber:
    """EventBus subscriber that sends email notifications for critical events.

    Gracefully degrades: if no email adapter is available, events are logged
    but no email is sent.
    """

    def __init__(self, email_adapter=None) -> None:
        """Initialize with an optional email adapter.

        Args:
            email_adapter: An EmailPort-compatible adapter instance. If None,
                no emails are sent but events are still logged.
        """
        self._adapter = email_adapter

    async def handle_critical_event(self, event: DomainEvent) -> None:
        """Handle a critical SaaS or pipeline event by sending a notification.

        Dispatches to the appropriate handler based on event type.
        """
        if self._adapter is None:
            logger.debug("Notification subscriber has no email adapter — skipping event %s", event.event_type.value)
            return

        event_type = event.event_type

        try:
            if event_type == SaaSEventType.WEBHOOK_PROCESSING_FAILED:
                await self._notify_webhook_failure(event)
            elif event_type == SaaSEventType.SPEND_CAP_EXCEEDED:
                await self._notify_spend_cap(event)
            elif event_type == SaaSEventType.PAYMENT_FAILED:
                await self._notify_payment_failure(event)
            elif event_type == SaaSEventType.PAYMENT_SUCCEEDED:
                await self._notify_payment_succeeded(event)
            elif event_type == SaaSEventType.SUBSCRIPTION_CANCELLED:
                await self._notify_subscription_cancelled(event)
            elif event_type == PipelineEventType.PIPELINE_FAILED:
                await self._notify_pipeline_failure(event)
            else:
                logger.debug("Notification subscriber: no handler for %s", event_type.value)
        except Exception as exc:
            logger.warning("Notification subscriber failed for %s: %s", event_type.value, exc)

    async def _notify_webhook_failure(self, event: DomainEvent) -> None:
        """Alert admins about a webhook processing failure."""
        meta = event.metadata
        provider = meta.get("provider", "unknown")
        error = meta.get("error", "unknown error")
        await self._send_admin_alert(
            subject=f"[Reasoner] Webhook Failure — {provider}",
            text=(
                f"A webhook from {provider} could not be processed.\n\n"
                f"Event type: {meta.get('event_type', 'N/A')}\n"
                f"Error: {error}\n"
                f"Timestamp: {event.timestamp}\n\n"
                "The failure has been recorded in the dead-letter store and can be replayed "
                "via POST /api/admin/dead-letter/replay."
            ),
        )

    async def _notify_spend_cap(self, event: DomainEvent) -> None:
        """Alert about a per-run spend cap being exceeded."""
        meta = event.metadata
        cap = meta.get("cap_amount", 0)
        total = meta.get("total_cost", 0)
        cap_type = meta.get("cap_type", "per_run")
        await self._send_admin_alert(
            subject=f"[Reasoner] Spend Cap Exceeded ({cap_type})",
            text=(
                f"The {cap_type} spend cap of ${cap:.2f} has been exceeded.\n\n"
                f"Current run cost: ${total:.2f}\n"
                f"Cap: ${cap:.2f}\n"
                f"Pipeline ID: {event.aggregate_id}\n"
                f"Timestamp: {event.timestamp}\n\n"
                "Further LLM calls in this pipeline have been halted."
            ),
        )

    async def _notify_payment_failure(self, event: DomainEvent) -> None:
        """Alert about a payment failure."""
        user_id = event.aggregate_id
        await self._send_admin_alert(
            subject="[Reasoner] Payment Failed",
            text=(
                f"A payment attempt failed for user {user_id}.\n"
                f"Timestamp: {event.timestamp}\n\n"
                "The user's subscription may need attention."
            ),
        )

    async def _notify_payment_succeeded(self, event: DomainEvent) -> None:
        """Log successful payment (informational — no admin alert needed)."""
        logger.info("Payment succeeded for user %s", event.aggregate_id)

    async def _notify_subscription_cancelled(self, event: DomainEvent) -> None:
        """Alert about a subscription cancellation."""
        await self._send_admin_alert(
            subject="[Reasoner] Subscription Cancelled",
            text=(
                f"User {event.aggregate_id} cancelled their subscription.\n"
                f"Timestamp: {event.timestamp}"
            ),
        )

    async def _notify_pipeline_failure(self, event: DomainEvent) -> None:
        """Alert about a pipeline failure (errors not from user input)."""
        meta = event.metadata
        error = meta.get("error", "unknown error")
        logger.warning("Pipeline failed for %s: %s", event.aggregate_id, error)

    async def _send_admin_alert(self, subject: str, text: str) -> None:
        """Send an email to the configured admin notification address."""
        if self._adapter is None:
            return
        to = self._get_admin_email()
        if not to:
            logger.debug("No admin email configured — skipping notification: %s", subject)
            return
        await self._adapter.send(EmailMessage(to=to, subject=subject, text_body=text))

    @staticmethod
    def _get_admin_email() -> str | None:
        """Return the admin notification email from settings."""
        try:
            from reasoner.core.settings import settings
            return settings.NOTIFICATION_EMAIL or None
        except Exception:
            return None
