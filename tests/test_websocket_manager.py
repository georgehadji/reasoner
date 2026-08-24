"""
Regression tests for BUG-002: WebSocketManager must protect mutable state
with an asyncio.Lock to prevent race conditions on concurrent connect,
disconnect, subscribe, and broadcast operations.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from reasoner.infrastructure.websocket.manager import (
    WebSocketManager,
    WebSocketMessage,
)


class FakeWebSocket:
    """Minimal mock that satisfies the methods we use."""
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.accept = AsyncMock()
        self.send_text = AsyncMock()
        self.send_json = AsyncMock()


class TestWebSocketManagerConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_connect_and_disconnect(self):
        """Rapid concurrent connect/disconnect should not lose state or crash."""
        manager = WebSocketManager()
        n = 20
        websockets = [FakeWebSocket() for _ in range(n)]

        async def connect_task(idx):
            await manager.connect(websockets[idx], f"conn-{idx}")

        async def disconnect_task(idx):
            manager.disconnect(f"conn-{idx}")

        # Interleave connects and disconnects
        tasks = []
        for i in range(n):
            tasks.append(asyncio.create_task(connect_task(i)))
            tasks.append(asyncio.create_task(disconnect_task(i)))

        await asyncio.gather(*tasks, return_exceptions=True)

        # All connections should be gone
        assert manager.get_connection_count() == 0
        for i in range(n):
            assert manager.get_subscriber_count(f"pipe-{i}") == 0

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_and_broadcast(self):
        """Concurrent subscription mutations during broadcast must not crash."""
        manager = WebSocketManager()
        ws = FakeWebSocket()
        await manager.connect(ws, "conn-0")

        async def subscriber_storm():
            for i in range(50):
                await manager.subscribe("conn-0", f"pipe-{i % 5}")
                await manager.unsubscribe("conn-0", f"pipe-{i % 5}")

        async def broadcaster():
            msg = WebSocketMessage(type="event", data={"x": 1})
            for i in range(50):
                await manager.broadcast_to_pipeline(f"pipe-{i % 5}", msg)

        await asyncio.gather(subscriber_storm(), broadcaster(), return_exceptions=True)

        manager.disconnect("conn-0")
        # disconnect() schedules an async task; yield to let it complete.
        await asyncio.sleep(0.1)
        assert manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_from_broadcast_send_error(self):
        """If send fails inside broadcast, disconnect must be safe."""
        manager = WebSocketManager()
        ws = FakeWebSocket()
        ws.send_text.side_effect = RuntimeError("boom")
        await manager.connect(ws, "conn-bad")
        await manager.subscribe("conn-bad", "pipe-1")

        msg = WebSocketMessage(type="event", data={"x": 1})
        # Should not raise despite send_text failing
        await manager.broadcast_to_pipeline("pipe-1", msg)

        # Give the async disconnect task time to run
        await asyncio.sleep(0.05)
        assert manager.get_connection_count() == 0
