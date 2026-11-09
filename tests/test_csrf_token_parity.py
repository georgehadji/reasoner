"""The backend accepts the CSRF tokens the Next.js proxy mints.

Without Caddy (local dev, OPS-8 setups), the Next proxy mints the csrf_token
cookie and forwards it as X-CSRF-Token. It used to mint ``ts:rand`` tokens,
while the backend accepts only ``expiry:nonce:sig16``, so with
CSRF_ENFORCE_BACKEND on every proxied POST was a 403. The vector below is pinned
in ui-next/src/lib/security-server.edge-cases.test.ts too; both sides must
produce and accept it.
"""

from __future__ import annotations

import hashlib
from unittest.mock import patch

from reasoner.api import csrf

SECRET = "test-secret-at-least-32-bytes-long!!"
#: expiry 4102444800 (year 2100), nonce "0123456789abcdef0123456789abcdef".
VECTOR = (
    "4102444800:0123456789abcdef0123456789abcdef:377f8b056c36c947"
    ".1a58f823bbbdea1de526ce5933cc31aa9f747a57e23b5a3faa6f4032c2114399"
)


def test_backend_accepts_the_shared_vector():
    with patch.object(csrf, "_CSRF_SECRET", hashlib.sha256(SECRET.encode()).digest()):
        assert csrf.verify_csrf_token(VECTOR) is True


def test_backend_rejects_the_old_ui_format():
    """The pre-fix UI shape, ``ts:rand``, signed correctly, is still refused."""
    key = hashlib.sha256(SECRET.encode()).digest()
    with patch.object(csrf, "_CSRF_SECRET", key):
        old = csrf.sign_csrf_token("1794234049:" + "a" * 48)
        assert csrf.verify_csrf_token(old) is False
