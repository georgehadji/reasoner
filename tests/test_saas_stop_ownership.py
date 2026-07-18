"""Tests for run cancellation ownership (SEC-016)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reasoner.api.run_state import RunStateStore
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter


@pytest.fixture
def run_store():
    """Fresh RunStateStore for each test."""
    store = RunStateStore()
    return store


@pytest.fixture
def stop_client(monkeypatch):
    """Build a TestClient with the stop endpoint mounted."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")
    adapter = LocalAuthAdapter(secret="test-secret-key-for-local-auth-adapter-only")
    set_auth_adapter(adapter)

    # Use a fresh RunStateManager with its own fallback store
    from reasoner.infrastructure.redis.run_state import RunStateManager
    fresh_manager = RunStateManager()

    # Patch both the source module AND the api module that imported it
    import reasoner.infrastructure.redis.run_state as redis_run_state_module
    import reasoner.api as api_module
    monkeypatch.setattr(redis_run_state_module, "_run_state_manager", fresh_manager)
    monkeypatch.setattr(api_module, "_run_store", fresh_manager)

    app = FastAPI()

    # Import the stop endpoint logic directly
    from reasoner.api import stop_pipeline
    from reasoner.api.auth_deps import require_csrf
    from reasoner.api.dependencies import get_optional_user

    app.post("/api/stop")(stop_pipeline)

    # Also need CSRF token generation
    from reasoner.api.csrf import sign_csrf_token

    client = TestClient(app)
    yield client, fresh_manager, sign_csrf_token
    set_auth_adapter(None)


@pytest.fixture
def user_a_token():
    adapter = LocalAuthAdapter(secret="test-secret-key-for-local-auth-adapter-only")
    return adapter.create_token("11111111-1111-1111-1111-111111111111", "user-a@example.com")


@pytest.fixture
def user_b_token():
    adapter = LocalAuthAdapter(secret="test-secret-key-for-local-auth-adapter-only")
    return adapter.create_token("22222222-2222-2222-2222-222222222222", "user-b@example.com")


# ── RunStateStore unit tests ──


@pytest.mark.asyncio
async def test_run_store_tracks_owner(run_store):
    """RunStateStore.add() stores user_id and get_owner() retrieves it."""
    await run_store.add("run-1", user_id="user-a")
    assert run_store.get_owner("run-1") == "user-a"


@pytest.mark.asyncio
async def test_run_store_owner_none_for_anonymous(run_store):
    """RunStateStore.add() without user_id stores None."""
    await run_store.add("run-1")
    assert run_store.get_owner("run-1") is None


@pytest.mark.asyncio
async def test_run_store_remove_clears_owner(run_store):
    """remove() clears the owner mapping."""
    await run_store.add("run-1", user_id="user-a")
    await run_store.remove("run-1")
    assert run_store.get_owner("run-1") is None


@pytest.mark.asyncio
async def test_run_store_reset_clears_all_owners(run_store):
    """reset() clears all owner mappings."""
    await run_store.add("run-1", user_id="user-a")
    await run_store.add("run-2", user_id="user-b")
    await run_store.reset()
    assert run_store.get_owner("run-1") is None
    assert run_store.get_owner("run-2") is None


# ── Route-level tests ──


def test_stop_specific_run_requires_auth_when_owned(
    stop_client, user_a_token, user_b_token
):
    """User B cannot cancel User A's run."""
    client, store, sign_csrf = stop_client
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        store.add("run-a", user_id="11111111-1111-1111-1111-111111111111")
    )

    csrf = sign_csrf("test-csrf")
    resp = client.post(
        "/api/stop?run_id=run-a",
        headers={
            "Authorization": f"Bearer {user_b_token}",
            "X-CSRF-Token": csrf,
        },
    )
    assert resp.status_code == 403
    assert "Cannot cancel another user's run" in resp.json()["detail"]


def test_stop_specific_run_owner_can_cancel(
    stop_client, user_a_token
):
    """User A can cancel their own run."""
    client, store, sign_csrf = stop_client
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        store.add("run-a", user_id="11111111-1111-1111-1111-111111111111")
    )

    csrf = sign_csrf("test-csrf")
    resp = client.post(
        "/api/stop?run_id=run-a",
        headers={
            "Authorization": f"Bearer {user_a_token}",
            "X-CSRF-Token": csrf,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == ["run-a"]


def test_stop_anonymous_run_requires_auth(
    stop_client, user_a_token
):
    """Any authenticated user can cancel an anonymous (no owner) run."""
    client, store, sign_csrf = stop_client
    import asyncio

    asyncio.get_event_loop().run_until_complete(store.add("run-anon"))

    csrf = sign_csrf("test-csrf")
    resp = client.post(
        "/api/stop?run_id=run-anon",
        headers={
            "Authorization": f"Bearer {user_a_token}",
            "X-CSRF-Token": csrf,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == ["run-anon"]


def test_stop_nonexistent_run_returns_not_found(
    stop_client, user_a_token
):
    """Stopping a non-existent run returns 200 with empty cancelled list."""
    client, store, sign_csrf = stop_client

    csrf = sign_csrf("test-csrf")
    resp = client.post(
        "/api/stop?run_id=nonexistent",
        headers={
            "Authorization": f"Bearer {user_a_token}",
            "X-CSRF-Token": csrf,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "not found"
    assert resp.json()["cancelled"] == []


def test_global_stop_requires_auth(stop_client):
    """Global stop (no run_id) requires authentication."""
    client, store, sign_csrf = stop_client
    import asyncio

    asyncio.get_event_loop().run_until_complete(store.add("run-1"))

    csrf = sign_csrf("test-csrf")
    resp = client.post(
        "/api/stop",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401
