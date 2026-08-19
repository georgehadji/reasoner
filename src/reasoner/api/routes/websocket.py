"""WebSocket endpoints for real-time pipeline updates.

Auth flow (security-remediation-plan.md Phase 3):
  1. An authenticated HTTPS caller gets a short-lived, single-use ticket
     from POST /api/websocket/ticket (application/services/ws_ticket.py).
  2. The browser opens the WebSocket passing that ticket via the
     Sec-WebSocket-Protocol header -- `new WebSocket(url, [ticket])` --
     never in the query string and never as a first post-connect message.
  3. Origin (ws_security.is_origin_allowed) and the per-IP connect rate
     limit (ws_security.check_connect_rate_limit) are checked alongside
     ticket redemption, all before `websocket.accept()`.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket

from reasoner.api.auth_deps import require_csrf
from reasoner.api.client_ip import get_client_ip
from reasoner.api.dependencies import get_current_user
from reasoner.core.settings import settings
from reasoner.application.services.ws_ticket import issue_ticket, redeem_ticket
from reasoner.domain.saas import User
from reasoner.infrastructure.websocket import get_websocket_manager, websocket_endpoint
from reasoner.infrastructure.websocket.ws_security import (
    check_connect_rate_limit,
    is_origin_allowed,
)

router = APIRouter()


@router.post("/api/websocket/ticket")
async def issue_websocket_ticket(
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
) -> dict[str, str]:
    """Issue a short-lived, single-use ticket for the next WebSocket connect.

    Authenticated the same way any other POST route is (bearer token +
    CSRF) -- the ticket only exists so the *WebSocket handshake itself*
    never has to carry a standing credential.
    """
    return {"ticket": issue_ticket(str(user.id))}


async def _authenticate_and_authorize_handshake(websocket: WebSocket) -> str | None:
    """Run every pre-``accept()`` check; return the resolved user_id, or
    None after already closing the socket with the appropriate reason."""
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(origin):
        await websocket.close(code=1008, reason="Origin not allowed")
        return None

    client_ip = get_client_ip(websocket)  # duck-types on .client/.headers, same as Request
    if not await check_connect_rate_limit(client_ip):
        await websocket.close(code=1008, reason="Too many connection attempts")
        return None

    ticket = websocket.headers.get("sec-websocket-protocol")
    if not ticket:
        await websocket.close(code=1008, reason="Missing connection ticket")
        return None
    user_id = await redeem_ticket(ticket)
    if not user_id:
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return None

    return user_id


@router.websocket("/ws")
async def websocket_connect(
    websocket: WebSocket,
    pipeline_id: str | None = None,
):
    """WebSocket endpoint for real-time pipeline updates."""
    user_id = await _authenticate_and_authorize_handshake(websocket)
    if not user_id:
        return
    ticket = websocket.headers.get("sec-websocket-protocol")
    await websocket_endpoint(
        websocket, pipeline_id,
        user_id=user_id, origin=websocket.headers.get("origin"), subprotocol=ticket,
    )


@router.websocket("/ws/pipeline/{pipeline_id}")
async def pipeline_websocket(
    websocket: WebSocket,
    pipeline_id: str,
):
    """WebSocket endpoint for a specific pipeline."""
    user_id = await _authenticate_and_authorize_handshake(websocket)
    if not user_id:
        return
    ticket = websocket.headers.get("sec-websocket-protocol")
    await websocket_endpoint(
        websocket, pipeline_id,
        user_id=user_id, origin=websocket.headers.get("origin"), subprotocol=ticket,
    )


@router.get("/api/websocket/stats")
async def get_websocket_stats(request: Request):
    """Aggregate WebSocket statistics (admin-only). Never returns pipeline
    identifiers -- only a connection count and a summed subscription
    count, not the per-pipeline breakdown."""
    admin_key = settings.ADMIN_API_KEY or ""
    provided = request.headers.get("X-Admin-Key", "")
    if not admin_key or not secrets.compare_digest(provided, admin_key):
        raise HTTPException(status_code=403, detail="Admin access required")
    manager = get_websocket_manager()
    return {
        "active_connections": manager.get_connection_count(),
        "total_subscriptions": sum(
            manager.get_subscriber_count(pipeline_id)
            for pipeline_id in manager.subscriptions.keys()
        ),
    }
