"""
Regression tests for BUG-004: _repair_truncated_json string quote overwrite.

Verifies that when an input string is truncated mid-value and no structural
boundary exists outside the open string, the closing quote is preserved and
not lost by the bracket-closing suffix assignment.
"""

from __future__ import annotations

import pytest

from reasoner.core.parsing import _repair_truncated_json


class TestBug004TruncatedJsonQuote:

    def test_bare_string_gets_closing_quote(self):
        """
        BUG-004 regression: A bare string value that was truncated mid-stream
        must receive a closing double-quote character.

        Without the fix: suffix='"}' then overwritten by suffix='}' →
        missing closing quote → invalid JSON syntax like: } instead of "}
        """
        text = '"bare string value truncated'
        result = _repair_truncated_json(text)
        assert result is not None, "Should produce a repaired string"
        # The result MUST contain a closing double-quote
        quote_count = result.count('"')
        assert quote_count == 2, (
            f"Expected 2 double-quotes (open + close), "
            f"got {quote_count} in {result!r}"
        )

    def test_object_with_truncated_string_value(self):
        """
        A JSON object truncated mid-value where the opening brace IS a
        structural boundary. The aggressive repair mode truncates back to
        the last structural boundary (the opening {), which produces an
        empty object {}.

        The critical invariant: quotes and braces must be balanced.
        """
        text = '{"key": "value that got truncated'
        result = _repair_truncated_json(text)
        assert result is not None
        # The aggressive repair strips back to the last structural boundary
        assert result == "{}", (
            f"Expected '{{}}' (aggressive truncation), got {result!r}"
        )
        # Invariant: braces balanced
        assert result.count("{") == result.count("}"), (
            f"Unbalanced braces: {result!r}"
        )

    def test_nested_object_truncated_in_string(self):
        """
        Deeply nested object truncated mid-string. Verify all levels close
        and the string terminator is present.
        """
        text = '{"outer": {"inner": "truncated value'
        result = _repair_truncated_json(text)
        assert result is not None
        # All braces and the string must close
        quote_count = result.count('"')
        assert quote_count % 2 == 0, (
            f"Unmatched quotes: {quote_count} quotes in {result!r}"
        )
        # Validity check: braces should be balanced
        opening_braces = result.count("{")
        closing_braces = result.count("}")
        assert opening_braces == closing_braces, (
            f"Unbalanced braces: {opening_braces} open, {closing_braces} close"
        )

    def test_already_balanced_returns_none(self):
        """Already-valid JSON should return None (no repair needed)."""
        result = _repair_truncated_json('{"a": "b"}')
        assert result is None, "Balanced JSON should return None"

    def test_truncated_array_value(self):
        """Array with a truncated string item."""
        text = '["item1", "item2 truncated'
        result = _repair_truncated_json(text)
        assert result is not None
        # String must be closed
        assert result.count('"') % 2 == 0, (
            f"Unmatched quotes in array: {result!r}"
        )
        # Brackets must balance
        assert result.count("[") == result.count("]"), (
            f"Unbalanced brackets: {result!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
