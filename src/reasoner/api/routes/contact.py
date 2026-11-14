"""Contact form endpoint.

POST /api/contact — deliver a /contact form submission to the team inbox.

The inbox is CONTACT_EMAIL, falling back to NOTIFICATION_EMAIL. With neither
set, or when the email adapter refuses, the route answers 503 so the form
shows a failure instead of a success that went nowhere.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit
from reasoner.application.ports.email_port import EmailMessage, EmailPort
from reasoner.core.settings import settings
from reasoner.infrastructure.email.resend_adapter import ResendEmailAdapter

logger = logging.getLogger(__name__)
router = APIRouter()

# Same shape the form checks client-side; the address is only used as reply_to.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Name and email end up in the subject line and reply_to: no line breaks or controls.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

Topic = Literal["Pilot", "Billing Issue", "Technical Support", "Feature Request", "Other"]


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=320)
    subject: Topic = "Other"
    message: str = Field(..., min_length=1, max_length=5_000)

    @field_validator("name", "message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("name")
    @classmethod
    def _single_line(cls, value: str) -> str:
        return _CONTROL_RE.sub(" ", value)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip()
        if _CONTROL_RE.search(value) or not _EMAIL_RE.match(value):
            raise ValueError("invalid email address")
        return value


def get_email_adapter() -> EmailPort:
    return ResendEmailAdapter()


@router.post("/api/contact")
async def submit_contact(
    req: ContactRequest,
    adapter: EmailPort = Depends(get_email_adapter),
    csrf_checked=Depends(require_csrf),
    rate_limit_checked=Depends(check_rate_limit),
):
    """Send a contact form submission. Anonymous: the form is public."""
    inbox = settings.CONTACT_EMAIL or settings.NOTIFICATION_EMAIL
    if not inbox:
        logger.warning("Contact form submission dropped: CONTACT_EMAIL is not configured")
        raise HTTPException(status_code=503, detail="Contact form is not configured")

    sent = await adapter.send(
        EmailMessage(
            to=inbox,
            subject=f"[Contact] {req.subject}: {req.name}",
            text_body=f"From: {req.name} <{req.email}>\nTopic: {req.subject}\n\n{req.message}",
            reply_to=req.email,
        )
    )
    if not sent:
        raise HTTPException(status_code=503, detail="Message could not be sent")
    return {"status": "sent"}
