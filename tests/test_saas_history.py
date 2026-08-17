"""Tests for history ownership isolation (SEC-007)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID

import pytest

from reasoner.api.history import HISTORY_DIR, HistoryEntry, _list_history, _save_history_entry
from reasoner.domain.saas import User


@pytest.fixture
def temp_history_dir(monkeypatch):
    """Use a temporary directory for history files."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        monkeypatch.setattr("reasoner.api.history.HISTORY_DIR", path)
        yield path


def test_history_entry_with_user_id(temp_history_dir):
    """HistoryEntry can store and retrieve user_id."""
    entry = HistoryEntry(
        id="test-123",
        user_id="user-a",
        problem="What is AI?",
        preset="research-budget",
        method="research",
        timestamp="2026-04-25T12:00:00",
        tokens={"input": 10, "output": 20, "total": 30},
        status="completed",
    )
    _save_history_entry(entry)

    loaded, total = _list_history()
    assert total == 1
    assert len(loaded) == 1
    assert loaded[0].user_id == "user-a"


def test_list_history_filters_by_user_id(temp_history_dir):
    """_list_history filters entries by user_id."""
    entries = [
        HistoryEntry(
            id="e1",
            user_id="user-a",
            problem="P1",
            preset="auto-budget",
            method="multi-perspective",
            timestamp="2026-04-25T12:00:00",
            tokens={"input": 1, "output": 1, "total": 2},
            status="completed",
        ),
        HistoryEntry(
            id="e2",
            user_id="user-b",
            problem="P2",
            preset="auto-budget",
            method="multi-perspective",
            timestamp="2026-04-25T12:01:00",
            tokens={"input": 1, "output": 1, "total": 2},
            status="completed",
        ),
        HistoryEntry(
            id="e3",
            user_id=None,
            problem="P3",
            preset="auto-budget",
            method="multi-perspective",
            timestamp="2026-04-25T12:02:00",
            tokens={"input": 1, "output": 1, "total": 2},
            status="completed",
        ),
    ]
    for e in entries:
        _save_history_entry(e)

    all_entries, total = _list_history()
    assert total == 3
    assert len(all_entries) == 3

    user_a_entries, user_a_total = _list_history(user_id="user-a")
    assert user_a_total == 1
    assert len(user_a_entries) == 1
    assert user_a_entries[0].id == "e1"

    user_b_entries, user_b_total = _list_history(user_id="user-b")
    assert user_b_total == 1
    assert len(user_b_entries) == 1
    assert user_b_entries[0].id == "e2"

    anon_entries, anon_total = _list_history(user_id="nonexistent")
    assert anon_total == 0
    assert len(anon_entries) == 0


def test_list_history_without_filter_includes_all(temp_history_dir):
    """_list_history without user_id returns all entries."""
    _save_history_entry(
        HistoryEntry(
            id="e1",
            user_id="user-x",
            problem="P1",
            preset="auto-budget",
            method="multi-perspective",
            timestamp="2026-04-25T12:00:00",
            tokens={"input": 1, "output": 1, "total": 2},
            status="completed",
        )
    )
    entries, total = _list_history()
    assert total == 1
    assert len(entries) == 1


# ── Route-level tests (require FastAPI TestClient) ──


@pytest.fixture
def history_client(temp_history_dir, monkeypatch):
    """Build a TestClient with history routes mounted."""
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from reasoner.api.routes.history import router as history_router
    from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
    from reasoner.infrastructure.auth import set_auth_adapter

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
        _save_history_entry(entry)

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
    _save_history_entry(entry)

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
    _save_history_entry(entry)

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
        _save_history_entry(
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
    remaining, remaining_total = _list_history()
    assert remaining_total == 1
    assert len(remaining) == 1
    assert remaining[0].id == "e2"
