"""Tests for the WebSocket handshake auth pipeline.

Rewritten for security-remediation-plan.md Phase 3: the query-string
``?token=`` path this file used to test (``_extract_bearer_token``,
``_authenticate_ws_token``) was removed entirely, not just supplemented --
see tests/test_ws_ticket.py for ticket issue/redeem coverage and
tests/test_websocket_security.py for the Origin/rate-limit/stats pieces.
This file covers the integrated handshake gate that composes all three
before ``accept()``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reasoner.api.routes.websocket import _authenticate_and_authorize_handshake
from reasoner.core.settings import settings

pytestmark = pytest.mark.unit


class FakeClient:
    def __init__(self, host: str = "1.2.3.4"):
        self.host = host


class FakeWebSocket:
    def __init__(self, headers: dict[str, str] | None = None, client_host: str = "1.2.3.4"):
        self.headers = headers or {}
        self.client = FakeClient(client_host)
        self.close = AsyncMock()


@pytest.fixture(autouse=True)
def _permissive_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Origin and rate-limit checks default to permissive so each test only
    exercises the one thing it's about; individual tests tighten as needed."""
    monkeypatch.setattr(settings, "CORS_ORIGINS", "")  # is_origin_allowed() -> True for any origin
    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 1_000_000)

    import reasoner.infrastructure.valkey.client as valkey_client_module

    class _NoopValkey:
        """Supports both the rate limiter's incr/expire and the ticket
        module's set(nx=...) -- both go through the same get_valkey_pool()."""

        def __init__(self) -> None:
            self._store: dict[str, str] = {}

        async def incr(self, key: str) -> int:
            return 1

        async def expire(self, key: str, ttl: int) -> None:
            return None

        async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
            if nx and key in self._store:
                return None
            self._store[key] = value
            return True

    monkeypatch.setattr(valkey_client_module, "get_valkey_pool", lambda: _NoopValkey())


async def test_disallowed_origin_closes_before_ticket_is_even_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.example.com")
    ws = FakeWebSocket(
        headers={"origin": "https://evil.example.com", "sec-websocket-protocol": "irrelevant"}
    )

    result = await _authenticate_and_authorize_handshake(ws)

    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs["reason"] == "Origin not allowed"


async def test_missing_ticket_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = FakeWebSocket(headers={"origin": "https://app.example.com"})

    result = await _authenticate_and_authorize_handshake(ws)

    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs["reason"] == "Missing connection ticket"


async def test_invalid_ticket_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = FakeWebSocket(
        headers={"origin": "https://app.example.com", "sec-websocket-protocol": "not-a-real-ticket"}
    )

    result = await _authenticate_and_authorize_handshake(ws)

    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs["reason"] == "Invalid or expired ticket"


async def test_valid_ticket_resolves_the_user_id_and_never_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CSRF_SECRET", "test-secret-do-not-reuse")
    from reasoner.application.services.ws_ticket import issue_ticket

    ticket = issue_ticket("user-42")
    ws = FakeWebSocket(
        headers={"origin": "https://app.example.com", "sec-websocket-protocol": ticket}
    )

    result = await _authenticate_and_authorize_handshake(ws)

    assert result == "user-42"
    ws.close.assert_not_awaited()


async def test_rate_limited_ip_is_rejected_before_ticket_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reasoner.infrastructure.valkey.client as valkey_client_module

    class _AlwaysOverLimit:
        async def incr(self, key: str) -> int:
            return 999

        async def expire(self, key: str, ttl: int) -> None:
            return None

    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(valkey_client_module, "get_valkey_pool", lambda: _AlwaysOverLimit())
    ws = FakeWebSocket(
        headers={"origin": "https://app.example.com", "sec-websocket-protocol": "irrelevant"}
    )

    result = await _authenticate_and_authorize_handshake(ws)

    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs["reason"] == "Too many connection attempts"
