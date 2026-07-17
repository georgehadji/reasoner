"""Tests for WebSocket pipeline ownership enforcement."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from reasoner.infrastructure.websocket.manager import (
    WebSocketManager,
    handle_websocket_message,
)


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        from starlette.websockets import WebSocketState
        self.client_state = WebSocketState.CONNECTED

    async def accept(self):
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


@pytest.mark.asyncio
async def test_dynamic_subscribe_ownership_enforced():
    """
    If User B tries to subscribe to User A's pipeline via WebSocket message,
    they should receive an error and not be subscribed.
    """
    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-1", metadata={"user_id": "user-b"})

    # Claim that pipeline-123 is owned by user-a.
    # handle_websocket_message does `from reasoner.pipeline_owner import
    # _get_pipeline_owner` inline at call time, so the patch target must be
    # the attribute on that module (not reasoner.api.history, which manager.py
    # never imports from).
    with patch(
        "reasoner.pipeline_owner._get_pipeline_owner",
        return_value="user-a",
    ):
        await handle_websocket_message(
            manager,
            "conn-1",
            {"type": "subscribe", "pipeline_id": "pipeline-123"},
        )

    # Should have received an error, not a subscribed confirmation
    assert len(ws.sent) == 2  # welcome + error
    assert '"type": "error"' in ws.sent[1]
    assert "Not authorized" in ws.sent[1]
    assert "pipeline-123" not in manager.subscriptions


@pytest.mark.asyncio
async def test_dynamic_subscribe_same_user_allowed():
    """
    A user subscribing to their own pipeline should succeed.
    """
    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-2", metadata={"user_id": "user-a"})

    with patch(
        "reasoner.pipeline_owner._get_pipeline_owner",
        return_value="user-a",
    ):
        await handle_websocket_message(
            manager,
            "conn-2",
            {"type": "subscribe", "pipeline_id": "pipeline-456"},
        )

    assert "pipeline-456" in manager.subscriptions
    assert '"type": "subscribed"' in ws.sent[1]
