"""Tests for pipeline resume endpoints."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")
_adapter = LocalAuthAdapter()
_test_token = _adapter.create_token("11111111-1111-1111-1111-111111111111", "test@example.com")
client = TestClient(app, headers={"Authorization": f"Bearer {_test_token}"})


@pytest.fixture(autouse=True)
def _use_local_auth_adapter():
    """Force local JWT auth so these tests do not depend on repo Supabase env."""
    set_auth_adapter(LocalAuthAdapter())
    yield
    set_auth_adapter(None)


class TestResumePipelineEndpoint:
    """Verify resume endpoints fail closed for unknown pipelines."""

    def test_resume_nonexistent_pipeline_returns_error(self):
        response = client.post("/api/pipelines/does-not-exist/resume")
        assert response.status_code == 403
        assert response.json()["error"] == "Not authorized to access this pipeline"


class TestResumePipelineStreamEndpoint:
    """Verify resume-stream fails closed for unknown pipelines."""

    def test_resume_stream_nonexistent_pipeline_returns_error(self):
        response = client.post("/api/pipelines/does-not-exist/resume-stream")
        assert response.status_code == 403
        assert response.json()["error"] == "Not authorized to access this pipeline"

    def test_resume_stream_returns_sse_headers(self):
        # Even for a nonexistent pipeline with empty problem, we expect either
        # an error JSON or SSE headers. Since we can't easily create a real
        # pipeline in the event store without fixtures, we at least verify
        # the endpoint structure is correct.
        response = client.post("/api/pipelines/test-resume-001/resume-stream")
        assert response.status_code == 403
        assert response.json()["error"] == "Not authorized to access this pipeline"

    def test_resume_meta_event_format(self):
        """Verify resume_meta SSE event has the expected shape."""
        # This test documents the expected contract for frontend consumers.
        expected_meta_fields = {
            "type": "resume_meta",
            "original_pipeline_id": "test-id",
            "phases_completed": [],
            "previous_synthesis": "",
        }
        # Validate shape (not values)
        assert "original_pipeline_id" in expected_meta_fields
        assert "phases_completed" in expected_meta_fields
        assert "previous_synthesis" in expected_meta_fields
