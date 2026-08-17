"""Pre-accept() WebSocket security checks — Origin validation and per-IP
connection rate limiting.

security-remediation-plan.md Phase 3 items 3-4. Both checks run before
``WebSocket.accept()`` in ``api/routes/websocket.py``, alongside the ticket
redemption in ``core/ws_ticket.py`` — a connection is never accepted while
still unverified.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def is_origin_allowed(origin: str | None) -> bool:
    """Reuses ``settings.cors_origins_list`` — the same allowlist already
    governs HTTP CORS, so WS Origin checking doesn't need a second config
    surface to keep in sync.

    A missing ``Origin`` header is rejected: browsers always send one on a
    WebSocket handshake, so its absence means a non-browser client that
    hasn't identified itself, not a legitimate same-origin request.
    """
    from reasoner.core.settings import settings

    if not origin:
        return False
    allowed = settings.cors_origins_list
    if not allowed:
        # No allowlist configured: match the existing permissive-when-
        # unconfigured posture of HTTP CORS rather than invent a stricter
        # rule here that the rest of the app doesn't enforce either.
        return True
    return origin in allowed


async def check_connect_rate_limit(client_ip: str) -> bool:
    """True if *client_ip* is still under the per-minute WS connection cap.

    Fails open on a Valkey outage: ``WebSocketManager``'s global
    ``max_connections`` cap remains as a backstop either way, so a degraded
    per-IP check isn't worse than the pre-Phase-3 baseline (no per-IP limit
    existed at all).
    """
    from reasoner.core.settings import settings
    from reasoner.infrastructure.valkey.client import get_valkey_pool

    window = int(time.time() // 60)
    key = f"ws_connect:{client_ip}:{window}"
    try:
        client = get_valkey_pool()
        count = await client.incr(key)
        await client.expire(key, 120)  # outlives the 60s window; cheap cleanup only
    except Exception as exc:
        logger.warning("WS connect rate limit check failed (Valkey unreachable); allowing: %s", exc)
        return True
    return count <= settings.WS_CONNECT_RATE_LIMIT_PER_MINUTE


__all__ = ["is_origin_allowed", "check_connect_rate_limit"]
