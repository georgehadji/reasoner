"""
Email Port — abstraction for sending transactional emails.

Port for EventBus-driven email notifications: webhook failures, spend cap
exceeded, payment failures, and other critical SaaS events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class EmailMessage:
    """A transactional email to be sent."""
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailPort(Protocol):
    """Port for sending transactional email notifications."""

    async def send(self, message: EmailMessage) -> bool:
        """Send a transactional email.

        Args:
            message: The email to send (to, subject, body).

        Returns:
            True if the email was accepted for delivery, False otherwise.
        """
        ...
