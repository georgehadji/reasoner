"""Tests for Pydantic request/response schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reasoner.api.schemas import RunRequest, FollowupRequest


class TestRunRequestValidation:
    """Validate RunRequest schema boundaries and sanitization."""

    def test_valid_minimal_request(self):
        req = RunRequest(problem="What is 2+2?", preset="multi-perspective-budget")
        assert req.problem == "What is 2+2?"
        assert req.preset == "multi-perspective-budget"
        assert req.top_k == 2  # default

    def test_top_k_accepted(self):
        req = RunRequest(problem="x", preset="multi-perspective-budget", top_k=5)
        assert req.top_k == 5

    def test_problem_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            RunRequest(problem="", preset="multi-perspective-budget")
        with pytest.raises(ValidationError):
            RunRequest(problem="   ", preset="multi-perspective-budget")

    def test_preset_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            RunRequest(problem="x", preset="")

    def test_invalid_preset_rejected(self):
        with pytest.raises(ValidationError):
            RunRequest(problem="x", preset="invalid-preset-name")

    def test_xss_stripping_in_problem(self):
        req = RunRequest(problem="<script>alert(1)</script> hello", preset="multi-perspective-budget")
        assert "<script>" not in req.problem

    def test_optional_fields_accepted(self):
        req = RunRequest(
            problem="x",
            preset="multi-perspective-budget",
            expert=True,
            web_search=False,
            smart_search=True,
            attachments=[{"file_id": "1", "filename": "f.txt", "mime_type": "text/plain", "extracted_text": "hello"}],
            client_run_id="run-123",
        )
        assert req.expert is True
        assert req.web_search is False
        assert req.smart_search is True
        assert len(req.attachments) == 1
        assert req.attachments[0].filename == "f.txt"

    def test_invalid_types_filtered(self):
        # These should not crash — invalid types are filtered by Pydantic
        with pytest.raises(ValidationError):
            RunRequest(problem=123, preset="multi-perspective-budget")  # type: ignore[arg-type]


class TestFollowupRequestValidation:
    """Validate FollowupRequest schema."""

    def test_valid_followup(self):
        req = FollowupRequest(
            question="Tell me more",
            conversation_id="conv-123",
            history=[{"role": "user", "content": "hi"}],
            previous_synthesis="Paris is the capital.",
        )
        assert req.question == "Tell me more"
        assert req.conversation_id == "conv-123"

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            FollowupRequest(
                question="",
                conversation_id="x",
                history=[],
                previous_synthesis="",
            )

    def test_source_type_validation(self):
        req = RunRequest(problem="x", preset="multi-perspective-budget", source_type="academic")
        assert req.source_type == "academic"

        with pytest.raises(ValidationError):
            RunRequest(problem="x", preset="multi-perspective-budget", source_type="invalid")
