"""Tests for parsing module bug fixes (BUG-004, BUG-005, BUG-006 regression)."""

import pytest
from reasoner.parsing import extract_json, safe_list, extract_solution_prose, ParseError


class TestExtractJsonRedosPrevention:
    """BUG-004 regression tests: extract_json must prevent ReDoS attacks."""

    def test_long_input_truncated(self):
        """Test that very long inputs are truncated before regex processing."""
        # Create a 200KB input (well over the 100KB limit)
        long_input = '{"key": "value"}' + ('x' * 200000)
        
        # Should not hang or crash - should either parse or raise ParseError
        try:
            result = extract_json(long_input)
            # If it parses, the JSON part should be extracted
            assert result == {"key": "value"}
        except ParseError:
            # Also acceptable - input was too malformed
            pass

    def test_malicious_nested_backticks(self):
        """Test handling of potentially malicious nested backtick patterns."""
        # Pattern that could cause backtracking
        malicious = '```' + ('`' * 1000) + 'test' + ('`' * 1000) + '```'
        
        try:
            extract_json(malicious)
        except ParseError:
            # Expected - not valid JSON
            pass

    def test_valid_json_still_works(self):
        """Test that valid JSON still parses correctly after fix."""
        valid = '{"task_type": "analytical", "rationale": "test"}'
        result = extract_json(valid)
        assert result["task_type"] == "analytical"

    def test_json_with_markdown_fences(self):
        """Test JSON with markdown fences still works."""
        fenced = '```json\n{"key": "value"}\n```'
        result = extract_json(fenced)
        assert result == {"key": "value"}


class TestSafeListDictHandling:
    """BUG-005 regression tests: safe_list must handle dict types correctly."""

    def test_dict_values_extracted(self):
        """Test that dict values are extracted instead of returning empty list."""
        d = {"key1": "value1", "key2": "value2"}
        result = safe_list(d)
        assert len(result) == 2
        assert "value1" in result
        assert "value2" in result

    def test_dict_with_non_string_values(self):
        """Test dict with numeric/boolean values."""
        d = {"a": 1, "b": 2.5, "c": True}
        result = safe_list(d)
        assert len(result) == 3
        assert "1" in result
        assert "2.5" in result
        assert "True" in result

    def test_empty_dict(self):
        """Test empty dict returns empty list."""
        result = safe_list({})
        assert result == []

    def test_list_still_works(self):
        """Test that list input still works correctly."""
        result = safe_list(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_string_still_works(self):
        """Test that string input still works correctly."""
        result = safe_list("single")
        assert result == ["single"]

    def test_none_returns_empty(self):
        """Test that None returns empty list."""
        result = safe_list(None)
        assert result == []

    def test_nested_dict_values(self):
        """Test dict with nested structures."""
        d = {"a": {"nested": "dict"}, "b": [1, 2, 3]}
        result = safe_list(d)
        assert len(result) == 2
        # Nested structures converted to string representation
        assert "{'nested': 'dict'}" in result or "{'nested': 'dict'}" in result


class TestExtractSolutionProseEmptyContent:
    """BUG-006 regression tests: extract_solution_prose must handle empty content."""

    def test_empty_solution_returns_none(self):
        """Test that empty [SOLUTION][/SOLUTION] returns None."""
        text = "[SOLUTION][/SOLUTION]"
        result = extract_solution_prose(text)
        assert result is None

    def test_whitespace_only_solution_returns_none(self):
        """Test that whitespace-only content returns None."""
        text = "[SOLUTION]   \n\t  [/SOLUTION]"
        result = extract_solution_prose(text)
        assert result is None

    def test_valid_solution_works(self):
        """Test that valid solution content is extracted."""
        text = "[SOLUTION]This is the answer[/SOLUTION]"
        result = extract_solution_prose(text)
        assert result == "This is the answer"

    def test_no_markers_returns_none(self):
        """Test that missing markers returns None."""
        text = "Just plain text without markers"
        result = extract_solution_prose(text)
        assert result is None

    def test_unicode_whitespace(self):
        """Test that unicode whitespace is handled correctly."""
        text = "[SOLUTION]\u00a0\u2003\u3000[/SOLUTION]"  # Various unicode spaces
        result = extract_solution_prose(text)
        assert result is None

    def test_solution_with_leading_trailing_whitespace(self):
        """Test that whitespace is stripped from valid solution."""
        text = "[SOLUTION]  \n  Answer with spaces  \n  [/SOLUTION]"
        result = extract_solution_prose(text)
        assert result == "Answer with spaces"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
