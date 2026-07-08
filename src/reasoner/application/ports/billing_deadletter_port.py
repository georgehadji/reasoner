"""
Billing Dead-Letter Port — Durable storage for failed webhook events.

Webhook processing failures are silently acknowledged (HTTP 200) to avoid
provider retry storms, but the failure MUST be recorded durably so it can
be replayed and alerted on.
"""

from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FailedWebhookEvent:
    """A webhook event that failed processing and was recorded to dead-letter."""
    provider: str
    event_type: str
    payload: dict
    error: str
    created_at: datetime | None = None
    replayed_at: datetime | None = None
    id: str | None = None


class BillingDeadLetterPort(Protocol):
    """Port for persisting webhook processing failures."""

    async def record_failure(
        self,
        provider: str,
        event_type: str,
        payload: dict,
        error: str,
    ) -> str:
        """Durably record a webhook processing failure.

        Args:
            provider: "stripe" or "paypal"
            event_type: The webhook event type/name
            payload: The raw event payload (redacted of secrets by caller)
            error: The exception message or error description

        Returns:
            The ID of the recorded failure record.
        """
        ...

    async def list_failures(
        self,
        provider: str | None = None,
        unreplayed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FailedWebhookEvent]:
        """List recorded failures with optional filtering.

        Args:
            provider: Filter by provider (None = all)
            unreplayed_only: Only return events that haven't been replayed
            limit: Max results
            offset: Pagination offset

        Returns:
            List of FailedWebhookEvent records.
        """
        ...

    async def mark_replayed(self, failure_id: str) -> bool:
        """Mark a recorded failure as successfully replayed.

        Args:
            failure_id: The ID of the failure record.

        Returns:
            True if the record was found and updated, False otherwise.
        """
        ...

    async def count_unreplayed(self) -> int:
        """Return the count of failures that haven't been replayed."""
        ...
