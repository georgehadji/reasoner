"""Tests for feedback storage and endpoints."""

import json
import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.core.settings import Settings
from reasoner.infrastructure.persistence.feedback_store import (
    FeedbackEntry,
    FeedbackStore,
)

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")

client = TestClient(app)


class TestFeedbackStore:
    """Unit tests for the SQLite feedback store."""

    @pytest.fixture
    def store(self, tmp_path):
        """Fresh FeedbackStore using a temporary database."""
        db_path = tmp_path / "feedback_test.db"
        return FeedbackStore(db_path=db_path)

    def test_init_creates_schema(self, store):
        """Schema should be created on initialization."""
        conn = store._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback_entries'"
        )
        assert cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_insert_and_retrieve(self, store):
        """Inserting an entry should return a row id and allow retrieval."""
        row_id = await store.insert(
            FeedbackEntry(
                conversation_id="conv-1",
                message_id="msg-1",
                rating="up",
            )
        )
        assert isinstance(row_id, int)
        assert row_id > 0

        entries = await store.get_entries(limit=10)
        assert len(entries) == 1
        assert entries[0].conversation_id == "conv-1"
        assert entries[0].rating == "up"

    @pytest.mark.asyncio
    async def test_insert_with_context(self, store):
        """Entries with context should round-trip correctly."""
        await store.insert(
            FeedbackEntry(
                conversation_id="conv-1",
                message_id="msg-2",
                rating="down",
                reason="incorrect",
                comment="Wrong answer",
                context={"message_length": 42, "has_images": False},
            )
        )
        entries = await store.get_entries()
        assert len(entries) == 1
        assert entries[0].context == {"message_length": 42, "has_images": False}

    @pytest.mark.asyncio
    async def test_stats_aggregation(self, store):
        """Stats should aggregate correctly over the time window."""
        # Seed data
        for i in range(3):
            await store.insert(FeedbackEntry(conversation_id="c", message_id=f"u{i}", rating="up"))
        for i in range(2):
            await store.insert(
                FeedbackEntry(
                    conversation_id="c",
                    message_id=f"d{i}",
                    rating="down",
                    reason="too_verbose" if i == 0 else "incorrect",
                    comment="Bad" if i == 0 else None,
                )
            )

        stats = await store.get_stats(days=30)
        assert stats.total_entries == 5
        assert stats.upvotes == 3
        assert stats.downvotes == 2
        assert stats.downvote_reasons == {"too_verbose": 1, "incorrect": 1}
        assert stats.avg_comment_length > 0

    @pytest.mark.asyncio
    async def test_jsonl_migration(self, tmp_path):
        """Existing JSONL should be backfilled and renamed on first init."""
        jsonl_path = tmp_path / "feedback.jsonl"
        jsonl_path.write_text(
            json.dumps({
                "timestamp": datetime.now(UTC).isoformat(),
                "conversation_id": "c1",
                "message_id": "m1",
                "rating": "up",
            }) + "\n" +
            json.dumps({
                "timestamp": datetime.now(UTC).isoformat(),
                "conversation_id": "c1",
                "message_id": "m2",
                "rating": "down",
                "reason": "outdated",
                "context": {"phase_count": 3},
            }) + "\n" +
            "this is not json\n",  # corrupt line
            encoding="utf-8",
        )

        db_path = tmp_path / "feedback_migrated.db"
        store = FeedbackStore(db_path=db_path, jsonl_path=jsonl_path)

        entries = await store.get_entries()
        assert len(entries) == 2
        assert entries[0].rating == "down"
        assert entries[1].rating == "up"

        # JSONL should be renamed
        assert not jsonl_path.exists()
        assert (tmp_path / "feedback.jsonl.migrated").exists()

    @pytest.mark.asyncio
    async def test_pagination(self, store):
        """Pagination should work correctly."""
        for i in range(5):
            await store.insert(FeedbackEntry(conversation_id="c", message_id=f"m{i}", rating="up"))

        page1 = await store.get_entries(limit=2, offset=0)
        assert len(page1) == 2

        page2 = await store.get_entries(limit=2, offset=2)
        assert len(page2) == 2

        page3 = await store.get_entries(limit=2, offset=4)
        assert len(page3) == 1


class TestFeedbackEndpoint:
    """Integration tests for the FastAPI feedback endpoints."""

    def test_submit_feedback(self):
        """POST /api/feedback should accept valid feedback."""
        response = client.post("/api/feedback", json={
            "conversation_id": "test-conv",
            "message_id": "test-msg",
            "rating": "up",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert "id" in data

    def test_submit_feedback_with_context(self):
        """POST /api/feedback should accept feedback with context."""
        response = client.post("/api/feedback", json={
            "conversation_id": "test-conv",
            "message_id": "test-msg-2",
            "rating": "down",
            "reason": "incorrect",
            "comment": "Wrong answer",
            "context": {"message_length": 100, "has_images": True},
        })
        assert response.status_code == 200

    def test_admin_stats_unauthorized(self):
        """GET /api/admin/feedback-stats without key should 401."""
        response = client.get("/api/admin/feedback-stats")
        assert response.status_code == 401

    def test_admin_stats_wrong_key(self):
        """GET /api/admin/feedback-stats with wrong key should 401."""
        response = client.get(
            "/api/admin/feedback-stats",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_admin_stats_authorized(self, monkeypatch):
        """GET /api/admin/feedback-stats with correct key should return stats."""
        monkeypatch.setattr(Settings, "ADMIN_API_KEY", "test-admin-key")

        from reasoner.infrastructure.auth import set_auth_adapter
        from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
        adapter = LocalAuthAdapter()
        # Force LocalAuthAdapter regardless of ambient SUPABASE_URL/ENVIRONMENT config —
        # get_auth_adapter() otherwise picks SupabaseAuthAdapter outside ENVIRONMENT=testing.
        set_auth_adapter(adapter)
        admin_token = adapter.create_token(
            "11111111-1111-1111-1111-111111111111",
            "admin@example.com",
            scopes=["admin"],
        )
        admin_client = TestClient(app, headers={"Authorization": f"Bearer {admin_token}"})

        # Submit some feedback first
        admin_client.post("/api/feedback", json={
            "conversation_id": "c1",
            "message_id": "m1",
            "rating": "up",
        })
        admin_client.post("/api/feedback", json={
            "conversation_id": "c1",
            "message_id": "m2",
            "rating": "down",
            "reason": "too_verbose",
        })

        response = admin_client.get(
            "/api/admin/feedback-stats?days=7",
            headers={"X-Admin-Key": "test-admin-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] >= 2
        assert data["upvotes"] >= 1
        assert data["downvotes"] >= 1
        assert "downvote_reasons" in data
        assert "avg_comment_length" in data
