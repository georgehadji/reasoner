"""WebSocket handshake security — security-remediation-plan.md Phase 3
items 3-5: Origin validation, per-IP connection rate limiting, and admin
stats no longer leaking pipeline IDs.
"""

from __future__ import annotations

import pytest

from reasoner.core.settings import settings
from reasoner.infrastructure.websocket.ws_security import (
    check_connect_rate_limit,
    is_origin_allowed,
)

pytestmark = pytest.mark.unit


# ── Origin validation ────────────────────────────────────────────────


def test_origin_on_the_allowlist_is_permitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.example.com,http://localhost:3000")

    assert is_origin_allowed("https://app.example.com") is True


def test_origin_not_on_the_allowlist_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.example.com")

    assert is_origin_allowed("https://evil.example.com") is False


def test_missing_origin_is_rejected_even_with_an_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Browsers always send Origin on a WS handshake -- its absence means a
    non-browser client that hasn't identified itself."""
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.example.com")

    assert is_origin_allowed(None) is False
    assert is_origin_allowed("") is False


def test_unconfigured_allowlist_matches_existing_cors_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No CORS_ORIGINS configured: match the existing permissive-when-
    unconfigured behavior of HTTP CORS rather than invent a stricter rule
    here that the rest of the app doesn't enforce."""
    monkeypatch.setattr(settings, "CORS_ORIGINS", "")

    assert is_origin_allowed("https://anything.example.com") is True


# ── per-IP connect rate limit ───────────────────────────────────────


class _FakeValkey:
    def __init__(self, fail: bool = False):
        self.counters: dict[str, int] = {}
        self.fail = fail

    async def incr(self, key: str) -> int:
        if self.fail:
            raise ConnectionError("valkey unreachable")
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int) -> None:
        if self.fail:
            raise ConnectionError("valkey unreachable")


def _patch_valkey(monkeypatch: pytest.MonkeyPatch, client: _FakeValkey) -> None:
    import reasoner.infrastructure.valkey.client as valkey_client_module

    monkeypatch.setattr(valkey_client_module, "get_valkey_pool", lambda: client)


async def test_connections_under_the_limit_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 5)
    _patch_valkey(monkeypatch, _FakeValkey())

    for _ in range(5):
        assert await check_connect_rate_limit("1.2.3.4") is True


async def test_the_nth_plus_one_connection_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 3)
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    results = [await check_connect_rate_limit("1.2.3.4") for _ in range(4)]

    assert results == [True, True, True, False]


async def test_different_ips_have_independent_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 1)
    _patch_valkey(monkeypatch, _FakeValkey())

    assert await check_connect_rate_limit("1.1.1.1") is True
    assert await check_connect_rate_limit("2.2.2.2") is True  # not affected by 1.1.1.1's usage


async def test_valkey_unreachable_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection-flood protection degrading isn't worse than the
    pre-Phase-3 baseline (no per-IP limit existed at all); the manager's
    global max_connections cap remains as a backstop either way."""
    monkeypatch.setattr(settings, "WS_CONNECT_RATE_LIMIT_PER_MINUTE", 1)
    _patch_valkey(monkeypatch, _FakeValkey(fail=True))

    assert await check_connect_rate_limit("1.2.3.4") is True


# ── admin stats: no pipeline IDs ────────────────────────────────────


async def test_admin_stats_response_never_contains_pipeline_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from reasoner.api.routes.websocket import router
    from reasoner.infrastructure.websocket.manager import get_websocket_manager

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")

    manager = get_websocket_manager()
    manager.subscriptions["pipeline-secret-123"] = {"conn-1", "conn-2"}
    manager.subscriptions["pipeline-secret-456"] = {"conn-3"}
    try:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/api/websocket/stats", headers={"X-Admin-Key": "test-admin-key"})

        assert response.status_code == 200
        body = response.json()
        assert "pipeline-secret-123" not in str(body)
        assert "pipeline-secret-456" not in str(body)
        assert body["total_subscriptions"] == 3
        assert "subscriptions" not in body  # the old per-pipeline map is gone, not just renamed
    finally:
        manager.subscriptions.pop("pipeline-secret-123", None)
        manager.subscriptions.pop("pipeline-secret-456", None)


async def test_admin_stats_still_requires_the_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from reasoner.api.routes.websocket import router

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/websocket/stats")

    assert response.status_code == 403
