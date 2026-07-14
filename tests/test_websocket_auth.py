"""Tests for WebSocket authentication."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from reasoner.api.routes.websocket import _authenticate_ws_token, _extract_bearer_token


class FakeWebSocket:
    def __init__(self, query_params=None, headers=None):
        self.query_params = query_params or {}
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_extract_bearer_token_from_query():
    ws = FakeWebSocket(query_params={"token": "abc123"})
    assert _extract_bearer_token(ws) == "abc123"


@pytest.mark.asyncio
async def test_extract_bearer_token_from_header():
    ws = FakeWebSocket(headers={"authorization": "Bearer xyz789"})
    assert _extract_bearer_token(ws) == "xyz789"


@pytest.mark.asyncio
async def test_extract_bearer_token_missing():
    ws = FakeWebSocket()
    assert _extract_bearer_token(ws) is None


@pytest.mark.asyncio
async def test_authenticate_ws_token_legacy():
    """Legacy API key auth should work for WebSocket tokens."""
    mock_key = AsyncMock()
    mock_key.key_hash = "hashed_key"

    with patch(
        "reasoner.auth.get_auth_manager",
        return_value=AsyncMock(
            authenticate=AsyncMock(return_value=mock_key)
        ),
    ):
        user_id = await _authenticate_ws_token("test-key")

    assert user_id == "hashed_key"


@pytest.mark.asyncio
async def test_authenticate_ws_token_invalid():
    """Invalid token should return None."""
    with patch(
        "reasoner.auth.get_auth_manager",
        return_value=AsyncMock(
            authenticate=AsyncMock(side_effect=Exception("bad key"))
        ),
    ):
        user_id = await _authenticate_ws_token("bad-key")

    assert user_id is None
