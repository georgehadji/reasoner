"""
Backend CSRF token generation and validation.

Implements a stateless Double-Submit Cookie pattern using HMAC-SHA256,
compatible with the Next.js frontend CSRF implementation in
ui-next/src/lib/security-server.ts.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

from reasoner.core.settings import settings


# Token validity window in seconds (24 hours)
_CSRF_TOKEN_MAX_AGE = 86400

# Per-process CSRF signing secret (rotates on restart — acceptable for stateless tokens).
# Computed once at import and reused by every sign/verify call below — when
# CSRF_SECRET is unset, _get_csrf_secret() returns a fresh random value on each
# call, so calling it again inside sign/verify would sign and verify with
# different secrets and every token would fail verification.


def _get_csrf_secret() -> bytes:
    """Get the CSRF signing secret. CSRF_SECRET must be set independently of ADMIN_API_KEY."""
    raw = settings.CSRF_SECRET or ""
    if not raw:
        if not settings.CSRF_ENFORCE_BACKEND:
            # Dev/CI: generate a random in-process secret (tokens won't survive restarts)
            return secrets.token_bytes(32)
        raise RuntimeError(
            "CSRF_SECRET must be set for CSRF protection. "
            "Set CSRF_SECRET in your .env file (do not reuse ADMIN_API_KEY)."
        )
    return hashlib.sha256(raw.encode()).digest()


_CSRF_SECRET = _get_csrf_secret()


def generate_csrf_token() -> str:
    """Generate a token that embeds a signed expiry timestamp."""
    expiry = int(time.time()) + _CSRF_TOKEN_MAX_AGE
    nonce = secrets.token_urlsafe(16)
    payload = f"{expiry}:{nonce}"
    sig = hmac.new(_CSRF_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def sign_csrf_token(token: str) -> str:
    """Sign a token with HMAC-SHA256. Returns 'token.signature_hex'."""
    sig = hmac.new(_CSRF_SECRET, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{sig}"


def verify_csrf_token(signed: str) -> bool:
    """Verify a signed CSRF token: signature validity + expiry check."""
    if not signed or "." not in signed:
        return False
    # Split on the last dot to handle token values that may contain dots
    token, _, provided_sig = signed.rpartition(".")
    if not token or not provided_sig:
        return False

    expected_sig = hmac.new(_CSRF_SECRET, token.encode("utf-8"), hashlib.sha256).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_sig, expected_sig):
        return False

    # Validate embedded signed expiry to enforce token max-age
    try:
        expiry, nonce, sig = token.rsplit(":", 2)
        payload = f"{expiry}:{nonce}"
        expected_payload_sig = hmac.new(
            _CSRF_SECRET, payload.encode(), hashlib.sha256
        ).hexdigest()[:16]
        if not secrets.compare_digest(sig, expected_payload_sig):
            return False
        return int(time.time()) < int(expiry)
    except (ValueError, IndexError):
        return False


def generate_signed_csrf_token() -> str:
    """Generate and sign a fresh CSRF token."""
    return sign_csrf_token(generate_csrf_token())
