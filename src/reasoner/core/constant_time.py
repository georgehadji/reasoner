"""Constant-time string comparison that survives non-ASCII input.

``hmac.compare_digest`` raises ``TypeError`` when either ``str`` holds a
non-ASCII character. Header values are latin-1 decoded, so a caller can put
one in ``X-CSRF-Token``, ``X-Admin-Key`` or ``Sec-WebSocket-Protocol`` and turn
a 403 into a 500. Comparing the UTF-8 bytes has no such failure.
"""

from __future__ import annotations

import hmac


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = ["constant_time_equals"]
