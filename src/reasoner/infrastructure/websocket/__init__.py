"""
WebSocket Package

Real-time event streaming via WebSocket connections.
"""

from reasoner.infrastructure.websocket.manager import (
    WebSocketManager,
    WebSocketMessage,
    get_websocket_manager,
    handle_websocket_message,
    setup_event_bus_integration,
    websocket_endpoint,
)

__all__ = [
    'WebSocketManager',
    'WebSocketMessage',
    'get_websocket_manager',
    'websocket_endpoint',
    'handle_websocket_message',
    'setup_event_bus_integration',
]
