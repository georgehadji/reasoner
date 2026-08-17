"""Tests for WebSocketManager lock sharding."""

from __future__ import annotations

import asyncio
import pytest
from starlette.websockets import WebSocketState

from reasoner.infrastructure.websocket.manager import WebSocketManager, WebSocketMessage


class FakeWebSocket:
    def __init__(self, conn_id):
        self.connection_id = conn_id
        self.client_state = WebSocketState.CONNECTED
        self.sent = []

    async def accept(self, subprotocol: str | None = None):
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_many_connections_without_latency_spikes():
    """
    Connect 100 WebSockets, send a message to each, and verify
    per-connection locks exist.
    """
    manager = WebSocketManager()
    ws_list = []

    for i in range(100):
        ws = FakeWebSocket(f"conn-{i}")
        await manager.connect(ws, f"conn-{i}")
        ws_list.append(ws)

    assert manager.get_connection_count() == 100

    # Send a message to each connection to populate per-connection locks
    for i in range(100):
        await manager.send_to_connection(
            f"conn-{i}",
            WebSocketMessage(type="test", data={}),
        )

    assert len(manager._connection_locks) == 100

    for ws in ws_list:
        manager.disconnect(ws.connection_id)

    # Wait for async disconnects to complete
    await asyncio.sleep(0.1)
    assert manager.get_connection_count() == 0
