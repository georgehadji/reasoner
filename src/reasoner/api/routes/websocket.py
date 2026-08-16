"""WebSocket endpoints for real-time pipeline updates."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, WebSocket

from reasoner.core.settings import settings

from reasoner.infrastructure.websocket import (
    get_websocket_manager,
    websocket_endpoint,
)

router = APIRouter()


def _extract_bearer_token(websocket: WebSocket) -> str | None:
    """Extract bearer token from query params or Authorization header."""
    token = websocket.query_params.get("token") or ""
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    return token or None


async def _authenticate_ws_token(token: str) -> str | None:
    """Authenticate a WebSocket token and return user_id if valid."""
    # Try JWT auth first, then legacy API key
    try:
        from reasoner.application.ports.auth_port import AuthPort
        from reasoner.application.services.auth_service import AuthService
        from reasoner.infrastructure.auth import get_auth_adapter
        adapter: AuthPort = get_auth_adapter()
        service = AuthService(adapter)
        user = await service.authenticate(token)
        if user:
            return str(user.id)
    except Exception:
        pass

    # Fallback to legacy API key auth
    try:
        from reasoner.auth import get_auth_manager
        auth_mgr = get_auth_manager()
        api_key = await auth_mgr.authenticate(token)
        if api_key:
            return getattr(api_key, "key_hash", None)
    except Exception:
        pass

    return None


@router.websocket("/ws")
async def websocket_connect(
    websocket: WebSocket,
    pipeline_id: str | None = None,
):
    """
    WebSocket endpoint for real-time pipeline updates.
    """
    token = _extract_bearer_token(websocket)
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    user_id = await _authenticate_ws_token(token)
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token")
        return
    await websocket_endpoint(websocket, pipeline_id)


@router.websocket("/ws/pipeline/{pipeline_id}")
async def pipeline_websocket(
    websocket: WebSocket,
    pipeline_id: str,
):
    """
    WebSocket endpoint for specific pipeline.
    """
    token = _extract_bearer_token(websocket)
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    user_id = await _authenticate_ws_token(token)
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token")
        return
    await websocket_endpoint(websocket, pipeline_id)


@router.get("/api/websocket/stats")
async def get_websocket_stats(request: Request):
    """Get WebSocket statistics (admin-only; contains pipeline identifiers)."""
    admin_key = settings.ADMIN_API_KEY or ""
    provided = request.headers.get("X-Admin-Key", "")
    if not admin_key or not secrets.compare_digest(provided, admin_key):
        raise HTTPException(status_code=403, detail="Admin access required")
    manager = get_websocket_manager()
    return {
        "active_connections": manager.get_connection_count(),
        "subscriptions": {
            pipeline_id: manager.get_subscriber_count(pipeline_id)
            for pipeline_id in manager.subscriptions.keys()
        },
    }
