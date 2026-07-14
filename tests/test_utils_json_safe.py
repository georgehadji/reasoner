"""Tests for safe JSON loading with depth limits."""

from __future__ import annotations

import json

import pytest

from reasoner.utils.json_safe import safe_json_loads, JSONDepthExceededError


class TestSafeJsonLoads:
    """Test JSON loading with depth protection."""

    def test_parses_valid_json(self):
        data = '{"key": "value", "num": 42}'
        result = safe_json_loads(data)
        assert result == {"key": "value", "num": 42}

    def test_parses_nested_json(self):
        data = '{"a": {"b": {"c": 1}}}'
        result = safe_json_loads(data)
        assert result["a"]["b"]["c"] == 1

    def test_rejects_excessively_deep_json(self):
        # Create a deeply nested JSON string
        deep = '{"a":' * 200 + '"bottom"' + '}' * 200
        with pytest.raises(JSONDepthExceededError):
            safe_json_loads(deep, max_depth=10)

    def test_allows_json_within_depth_limit(self):
        data = '{"a": {"b": {"c": 1}}}'
        result = safe_json_loads(data, max_depth=5)
        assert result["a"]["b"]["c"] == 1

    def test_rejects_malformed_json(self):
        with pytest.raises(json.JSONDecodeError):
            safe_json_loads("not json")

    def test_rejects_truncated_json(self):
        with pytest.raises(json.JSONDecodeError):
            safe_json_loads('{"key": "value"')

    def test_parses_json_bytes(self):
        data = b'{"key": "value"}'
        result = safe_json_loads(data)
        assert result == {"key": "value"}

    def test_parses_empty_object(self):
        assert safe_json_loads("{}") == {}

    def test_parses_empty_array(self):
        assert safe_json_loads("[]") == []

    def test_parses_null(self):
        assert safe_json_loads("null") is None

    def test_parses_boolean(self):
        assert safe_json_loads("true") is True
        assert safe_json_loads("false") is False

    def test_parses_number(self):
        assert safe_json_loads("42") == 42
        assert safe_json_loads("3.14") == 3.14
