"""Short-lived, single-use WebSocket connection tickets.

Modeled on api/csrf.py's HMAC-with-embedded-expiry pattern, but purpose-
scoped: a leaked CSRF token must not be replayable as a WS ticket, so this
derives its own key material from CSRF_SECRET via domain separation rather
than sharing csrf.py's raw secret bytes.

A ticket is deliberately not just short-TTL -- redemption also does a
Valkey SET NX on the embedded nonce, so a ticket can't be replayed even
within its validity window. That matters here specifically because the
ticket travels via the Sec-WebSocket-Protocol header, which (unlike a
bearer token in an Authorization header) can end up visible in browser
devtools network logs a user might screen-share or paste into a bug report.

security-remediation-plan.md Phase 3 item 2: replaces the query-string
``?token=`` a WebSocket used to carry a real, long-lived access token in.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time

from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

_TICKET_DOMAIN_SEPARATOR = b"ws-ticket-v1"


def _get_ticket_secret() -> bytes:
    raw = settings.CSRF_SECRET or ""
    if not raw:
        if not settings.CSRF_ENFORCE_BACKEND:
            # Dev/CI: generate a random in-process secret, same posture as
            # csrf.py's own fallback. Tickets won't survive a restart.
            return secrets.token_bytes(32)
        raise RuntimeError(
            "CSRF_SECRET must be set to issue WebSocket tickets (reused as key "
            "material, domain-separated from CSRF tokens -- do not set a "
            "separate secret for this)."
        )
    # HMAC with a fixed domain-separator payload, not a bare hash of the raw
    # secret: this key must not equal csrf.py's _get_csrf_secret() output,
    # so a CSRF token's signature can't be replayed as a WS ticket.
    return hmac.new(raw.encode(), _TICKET_DOMAIN_SEPARATOR, hashlib.sha256).digest()


def issue_ticket(user_id: str) -> str:
    """Issue a signed, short-lived, single-use ticket for *user_id*."""
    secret = _get_ticket_secret()
    expiry = int(time.time()) + settings.WS_TICKET_TTL_SECONDS
    nonce = secrets.token_urlsafe(16)
    payload = f"{user_id}:{expiry}:{nonce}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


async def redeem_ticket(ticket: str) -> str | None:
    """Verify and consume *ticket* once, returning the embedded user_id.

    Fails closed on every error path, including a Valkey outage: unlike
    application.services.anonymous_trial_policy (an abuse counter, safe to
    fail open), this gates authentication itself -- "can't verify single-use"
    must mean "reject", not "allow".
    """
    if not ticket or ticket.count(":") < 3:
        return None

    # Peel from the right so a user_id that happens to contain a colon
    # (not expected today, but not a format guarantee either) still parses.
    try:
        rest, provided_sig = ticket.rsplit(":", 1)
        rest, nonce = rest.rsplit(":", 1)
        user_id, expiry_str = rest.rsplit(":", 1)
    except ValueError:
        return None
    if not user_id or not nonce or not provided_sig:
        return None

    secret = _get_ticket_secret()
    payload = f"{user_id}:{expiry_str}:{nonce}"
    expected_sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        expiry = int(expiry_str)
    except ValueError:
        return None
    if int(time.time()) >= expiry:
        return None

    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool

        client = get_valkey_pool()
        redeemed = await client.set(
            f"ws_ticket_used:{nonce}", "1", nx=True, ex=settings.WS_TICKET_TTL_SECONDS
        )
    except Exception:
        logger.warning(
            "WS ticket single-use check failed (Valkey unreachable); denying", exc_info=True
        )
        return None

    if not redeemed:
        logger.warning("WS ticket replay attempt detected (nonce already redeemed)")
        return None

    return user_id


__all__ = ["issue_ticket", "redeem_ticket"]
