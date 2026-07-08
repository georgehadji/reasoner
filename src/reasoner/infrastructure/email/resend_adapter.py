"""
Resend Email Adapter — sends transactional emails via the Resend API.

Implements EmailPort using Resend's simple HTTP API.
Gracefully degrades when RESEND_API_KEY is not configured.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from reasoner.application.ports.email_port import EmailMessage, EmailPort
from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

_RESEND_API_BASE = "https://api.resend.com"
_DEFAULT_FROM = "Reasoner <notifications@reasoner.app>"


class ResendEmailAdapter:
    """Send transactional emails via Resend API.

    Falls back to logging the email body when the API key is not configured,
    so the system works without email in development.
    """

    def __init__(self, api_key: str | None = None, from_address: str | None = None) -> None:
        self._api_key = api_key or settings.RESEND_API_KEY
        self._from = from_address or settings.RESEND_FROM_ADDRESS or _DEFAULT_FROM
        self._enabled = bool(self._api_key)

    async def send(self, message: EmailMessage) -> bool:
        """Send a transactional email via Resend API.

        Args:
            message: The email to send.

        Returns:
            True if accepted, False if skipped (no key) or failed.
        """
        if not self._enabled:
            logger.info(
                "Email not sent (no RESEND_API_KEY configured). Would have sent to %s: %s",
                message.to, message.subject,
            )
            return False

        payload: dict[str, Any] = {
            "from": self._from,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body:
            payload["html"] = message.html_body

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                resp = await client.post(
                    f"{_RESEND_API_BASE}/emails",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    content=json.dumps(payload),
                )
                if resp.status_code in (200, 201):
                    logger.debug("Email sent to %s: %s", message.to, message.subject)
                    return True
                else:
                    logger.warning(
                        "Resend API returned %s for email to %s: %s",
                        resp.status_code, message.to, resp.text,
                    )
                    return False
        except httpx.TimeoutException:
            logger.warning("Timeout sending email to %s: %s", message.to, message.subject)
            return False
        except Exception as exc:
            logger.warning("Failed to send email to %s: %s", message.to, exc)
            return False
