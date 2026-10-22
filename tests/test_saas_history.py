"""Tests for history ownership isolation (SEC-007)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from uuid import UUID

import pytest

from reasoner.api.history import HistoryEntry, history_repo


@pytest.fixture
def temp_history_dir(monkeypatch):
    """Use a temporary directory for history files."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        monkeypatch.setattr("reasoner.api.history.HISTORY_DIR", path)
        yield path


def _entry(entry_id: str, user_id: str | None, timestamp: str) -> HistoryEntry:
    return HistoryEntry(
        id=entry_id, user_id=user_id, problem="P", preset="auto-budget",
        method="multi-perspective", timestamp=timestamp,
        tokens={"input": 1, "output": 1, "total": 2}, status="completed",
    )


async def _save(entry: HistoryEntry) -> None:
    await history_repo().save(entry.model_dump())


def _save_sync(entry: HistoryEntry) -> None:
    asyncio.run(_save(entry))


@pytest.mark.asyncio
async def test_history_entry_with_user_id(temp_history_dir):
    """A saved entry comes back for its owner with its user_id."""
    await _save(_entry("test-123", "user-a", "2026-04-25T12:00:00"))

    loaded, total = await history_repo().list("user-a", 50, 0)
    assert total == 1
    assert loaded[0]["user_id"] == "user-a"


@pytest.mark.asyncio
async def test_list_history_is_scoped_to_the_owner(temp_history_dir):
    """Each owner lists only their own entries; anonymous runs are their own owner."""
    for e in (
        _entry("e1", "user-a", "2026-04-25T12:00:00"),
        _entry("e2", "user-b", "2026-04-25T12:01:00"),
        _entry("e3", None, "2026-04-25T12:02:00"),
    ):
        await _save(e)

    for owner, expected in (("user-a", "e1"), ("user-b", "e2"), (None, "e3")):
        entries, total = await history_repo().list(owner, 50, 0)
        assert total == 1
        assert [e["id"] for e in entries] == [expected]

    entries, total = await history_repo().list("nonexistent", 50, 0)
    assert total == 0 and entries == []


# ── Route-level tests (require FastAPI TestClient) ──


@pytest.fixture
def history_client(temp_history_dir, monkeypatch):
    """Build a TestClient with history routes mounted."""

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from reasoner.api.routes.history import router as history_router
    from reasoner.infrastructure.auth import set_auth_adapter
    from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter

    # Ensure JWT secret is strong enough
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")

    app = FastAPI()
    app.include_router(history_router)

    # Create a token for a known user
    adapter = LocalAuthAdapter()
    # Force LocalAuthAdapter regardless of ambient SUPABASE_URL/ENVIRONMENT config —
    # get_auth_adapter() otherwise picks SupabaseAuthAdapter outside ENVIRONMENT=testing.
    # get_auth_adapter() is a global singleton independent of which FastAPI app
    # instance the routes are mounted on, so this is required even for this
    # standalone `app`, not just reasoner.api.app.
    set_auth_adapter(adapter)

    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {adapter.create_token(str(UUID('11111111-1111-1111-1111-111111111111')), 'user-a@example.com')}"
    yield client
    set_auth_adapter(None)


def test_get_history_requires_auth(history_client):
    """GET /api/history returns 401 without auth."""
    from fastapi.testclient import TestClient
    # Remove auth header
    no_auth_client = TestClient(history_client.app)
    resp = no_auth_client.get("/api/history")
    assert resp.status_code == 401


def test_get_history_returns_only_user_entries(history_client, temp_history_dir):
    """Authenticated user only sees their own history."""
    # Seed entries for two users
    for uid, eid in [("11111111-1111-1111-1111-111111111111", "e1"), ("22222222-2222-2222-2222-222222222222", "e2")]:
        entry = HistoryEntry(
            id=eid,
            user_id=uid,
            problem=f"Problem {eid}",
            preset="auto-budget",
            method="multi-perspective",
            timestamp="2026-04-25T12:00:00",
            tokens={"input": 1, "output": 1, "total": 2},
            status="completed",
        )
        _save_sync(entry)

    resp = history_client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["id"] == "e1"


def test_get_history_entry_not_owned_returns_404(history_client, temp_history_dir):
    """User cannot access another user's history entry."""
    entry = HistoryEntry(
        id="e2",
        user_id="22222222-2222-2222-2222-222222222222",
        problem="Secret",
        preset="auto-budget",
        method="multi-perspective",
        timestamp="2026-04-25T12:00:00",
        tokens={"input": 1, "output": 1, "total": 2},
        status="completed",
    )
    _save_sync(entry)

    resp = history_client.get("/api/history/e2")
    assert resp.status_code == 404


def test_delete_history_entry_not_owned_returns_404(history_client, temp_history_dir):
    """User cannot delete another user's history entry."""
    entry = HistoryEntry(
        id="e2",
        user_id="22222222-2222-2222-2222-222222222222",
        problem="Secret",
        preset="auto-budget",
        method="multi-perspective",
        timestamp="2026-04-25T12:00:00",
        tokens={"input": 1, "output": 1, "total": 2},
        status="completed",
    )
    _save_sync(entry)

    # Need CSRF token for delete
    from reasoner.api.csrf import sign_csrf_token
    csrf_token = sign_csrf_token("test-csrf")
    resp = history_client.delete(
        "/api/history/e2",
        headers={**history_client.headers, "X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 404


def test_clear_history_only_clears_own_entries(history_client, temp_history_dir):
    """Clear only removes entries belonging to the authenticated user."""
    for uid, eid in [("11111111-1111-1111-1111-111111111111", "e1"), ("22222222-2222-2222-2222-222222222222", "e2")]:
        _save_sync(
            HistoryEntry(
                id=eid,
                user_id=uid,
                problem=f"Problem {eid}",
                preset="auto-budget",
                method="multi-perspective",
                timestamp="2026-04-25T12:00:00",
                tokens={"input": 1, "output": 1, "total": 2},
                status="completed",
            )
        )

    from reasoner.api.csrf import sign_csrf_token
    csrf_token = sign_csrf_token("test-csrf")
    resp = history_client.delete(
        "/api/history",
        headers={**history_client.headers, "X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cleared"] == 1, f"Expected 1 cleared, got {data}"

    # Verify other user's entry remains
    other = "22222222-2222-2222-2222-222222222222"
    remaining, remaining_total = asyncio.run(history_repo().list(other, 50, 0))
    assert remaining_total == 1
    assert len(remaining) == 1
    assert remaining[0]["id"] == "e2"
