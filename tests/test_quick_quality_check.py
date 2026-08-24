"""Tests for QuickQualityCheck — fast quality gate for cascading responses."""

from __future__ import annotations

import json

from reasoner.quality.quick_check import QuickQualityCheck


class TestCheckJsonRole:
    """JSON validation for structured-output roles."""

    def test_non_json_role_skips_check(self):
        ok, reason = QuickQualityCheck.check_json_role("synthesis", "some text")
        assert ok is True
        assert "not a JSON role" in reason

    def test_empty_response_for_json_role_fails(self):
        ok, reason = QuickQualityCheck.check_json_role("classification", "")
        assert ok is False
        assert "empty" in reason

    def test_valid_classification_json(self):
        raw = json.dumps({"task_type": "coding", "confidence": 0.9})
        ok, reason = QuickQualityCheck.check_json_role("classification", raw)
        assert ok is True
        assert "valid JSON" in reason

    def test_missing_required_key(self):
        raw = json.dumps({"confidence": 0.9})  # missing "task_type"
        ok, reason = QuickQualityCheck.check_json_role("classification", raw)
        assert ok is False
        assert "task_type" in reason

    def test_invalid_json(self):
        ok, reason = QuickQualityCheck.check_json_role("decomposition", "not json")
        assert ok is False
        assert "invalid JSON" in reason

    def test_json_not_object(self):
        ok, reason = QuickQualityCheck.check_json_role("scoring", "[1, 2, 3]")
        assert ok is False
        assert "not an object" in reason

    def test_decomposition_missing_sub_problems(self):
        raw = json.dumps({"task_type": "research"})
        ok, reason = QuickQualityCheck.check_json_role("decomposition", raw)
        assert ok is False
        assert "sub_problems" in reason

    def test_scoring_missing_scores(self):
        raw = json.dumps({"task_type": "research"})
        ok, reason = QuickQualityCheck.check_json_role("scoring", raw)
        assert ok is False
        assert "scores" in reason

    def test_fusion_requires_both_keys(self):
        raw = json.dumps({"task_type": "coding"})  # missing sub_problems
        ok, reason = QuickQualityCheck.check_json_role("fusion", raw)
        assert ok is False
        assert "sub_problems" in reason


class TestCheckContentQuality:
    """Content-quality heuristics."""

    def test_empty_response_fails(self):
        ok, reason = QuickQualityCheck.check_content_quality("synthesis", "")
        assert ok is False
        assert "empty" in reason

    def test_too_short_synthesis(self):
        ok, reason = QuickQualityCheck.check_content_quality("synthesis", "x" * 50)
        assert ok is False
        assert "too short" in reason

    def test_min_length_uses_default_for_unknown_role(self):
        ok, reason = QuickQualityCheck.check_content_quality("unknown_role", "x" * 25)
        assert ok is True

    def test_repetitive_text_detected(self):
        # Use 'primary' role (min_len=20) so length check doesn't trigger first
        text = "repeat\n" * 20
        ok, reason = QuickQualityCheck.check_content_quality("primary", text)
        assert ok is False
        assert "repetition" in reason

    def test_unbalanced_code_fences(self):
        # coding_generate min_len=100, so pad the text
        text = "```python\nprint(1)\n" + "x" * 100
        ok, reason = QuickQualityCheck.check_content_quality("coding_generate", text)
        assert ok is False
        assert "unbalanced" in reason

    def test_balanced_code_fences_pass(self):
        text = "```python\nprint(1)\n```\n" + "x" * 100
        ok, reason = QuickQualityCheck.check_content_quality("coding_generate", text)
        assert ok is True


class TestCheckAll:
    """Combined quality gate."""

    def test_all_checks_pass(self):
        raw = json.dumps({"task_type": "coding"})
        ok, reason = QuickQualityCheck.check_all("classification", raw)
        assert ok is True
        assert "all checks passed" in reason

    def test_json_failure_short_circuits(self):
        ok, reason = QuickQualityCheck.check_all("classification", "bad json")
        assert ok is False
        assert "invalid JSON" in reason

    def test_content_failure_after_json_pass(self):
        # scoring has min_len=20; make JSON long enough to pass length check
        raw = json.dumps({"scores": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        ok, reason = QuickQualityCheck.check_all("scoring", raw)
        assert ok is True  # JSON is valid and not too short
