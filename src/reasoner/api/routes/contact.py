"""Contact / support endpoint.

POST /api/contact — deliver a support request to the operator.

The contact page used to call a client-side handler that did nothing, then told
the user "our support team will get back to you within 24 hours". Every message
was discarded, and there was no support address published anywhere as a
fallback — which also left GDPR data-subject requests with no channel.

This endpoint tells the truth in both directions: it returns 200 only when the
message was actually accepted for delivery, and 503 with the configured support
address when email is not set up, so the UI can show somewhere real to write to.
"""

from __future__ import annotations

import logging
from typing import Literal

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit
from reasoner.core.sanitization import sanitize_for_prompt
from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

Topic = Literal["Billing Issue", "Technical Support", "Feature Request", "Other"]

# Deliberately not pydantic's EmailStr: that pulls in the optional
# `email-validator` dependency, which this project does not ship. A reply-to
# address on a contact form only needs to be plausible — the real test of
# validity is whether the reply arrives.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class ContactRequest(BaseModel):
    """Mirrors the form in ui-next/src/app/contact/page.tsx."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    topic: Topic = "Other"
    message: str = Field(min_length=1, max_length=5000)

    model_config = {"extra": "forbid"}

    @field_validator("email")
    @classmethod
    def _plausible_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v

    @field_validator("name", "message")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        # This text is operator-facing, not model-facing, but it is still
        # untrusted input arriving from an unauthenticated endpoint.
        return sanitize_for_prompt(v)


@router.post("/api/contact")
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    _rate_limited=Depends(check_rate_limit),
    _csrf=Depends(require_csrf),
):
    destination = settings.NOTIFICATION_EMAIL
    if not destination:
        logger.warning(
            "Contact form submission dropped — NOTIFICATION_EMAIL is not configured"
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Support messages aren't set up yet, so this form can't reach anyone. "
                "Please email us directly instead."
            ),
        )

    from reasoner.application.ports.email_port import EmailMessage
    from reasoner.infrastructure.email.resend_adapter import ResendEmailAdapter

    body = (
        f"Topic: {payload.topic}\n"
        f"From:  {payload.name} <{payload.email}>\n"
        f"\n"
        f"{payload.message}\n"
    )

    delivered = await ResendEmailAdapter().send(
        EmailMessage(
            to=destination,
            subject=f"[Reasoner support] {payload.topic} — {payload.name}",
            text_body=body,
        )
    )

    if not delivered:
        # send() returns False when RESEND_API_KEY is absent or the API rejected
        # the message. Either way it did not reach anyone, so don't claim it did.
        raise HTTPException(
            status_code=503,
            detail=(
                "We couldn't deliver your message right now. Please email us "
                "directly and we'll pick it up."
            ),
        )

    return {"status": "sent"}
