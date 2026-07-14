"""Tests for CSRF token resilience against clock jumps."""

from __future__ import annotations

import time
from unittest.mock import patch

from reasoner.api.csrf import generate_csrf_token, verify_csrf_token, sign_csrf_token


def test_csrf_token_valid():
    """A freshly generated token should be valid."""
    token = generate_csrf_token()
    signed = sign_csrf_token(token)
    assert verify_csrf_token(signed) is True


def test_csrf_token_rejects_clock_jump_forward():
    """
    If the system clock jumps forward past the expiry,
    the token should be rejected even though it was recently generated.
    """
    token = generate_csrf_token()
    signed = sign_csrf_token(token)

    # Simulate clock jumping forward by 25 hours (past the 24h max age)
    with patch("reasoner.api.csrf.time.time", return_value=time.time() + 90000):
        assert verify_csrf_token(signed) is False


def test_csrf_token_rejects_tampered_expiry():
    """Tampering with the expiry payload should invalidate the token."""
    token = generate_csrf_token()
    signed = sign_csrf_token(token)

    # Tamper with the signed token (modify expiry)
    parts = signed.rsplit(".", 1)
    tampered_token = "9999999999:" + token.split(":", 1)[1]
    tampered_signed = f"{tampered_token}.{parts[1]}"

    assert verify_csrf_token(tampered_signed) is False
