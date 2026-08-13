"""Tests for parsing module."""

import pytest
from reasoner.parsing import extract_json, strip_perplexity_citations, strip_prose_preamble, ParseError


class TestStripPerplexityCitations:
    """Test Perplexity Sonar citation removal."""
    
    def test_removes_citation_markers(self):
        text = 'This is a response [1] with citations [2] and [3].'
        result = strip_perplexity_citations(text)
        assert '[1]' not in result
        assert '[2]' not in result
        assert '[3]' not in result
        assert 'This is a response' in result
    
    def test_removes_sources_section(self):
        text = 'Response text.\n\nSources:\n[1] https://example.com\n[2] https://test.com'
        result = strip_perplexity_citations(text)
        assert 'Sources:' not in result
        assert 'example.com' not in result
        assert 'Response text' in result
    
    def test_removes_citations_section(self):
        text = 'Response text.\n\nCitations:\n[1] Source 1\n[2] Source 2'
        result = strip_perplexity_citations(text)
        assert 'Citations:' not in result
        assert 'Source 1' not in result
        assert 'Response text' in result


class TestStripProsePreamble:
    """Test prose preamble removal."""
    
    def test_removes_here_is_json(self):
        text = 'Here is the JSON:\n{"key": "value"}'
        result = strip_prose_preamble(text)
        assert 'Here is the JSON:' not in result
        assert '{"key": "value"}' in result
    
    def test_removes_sure_here_is(self):
        text = 'Sure! Here is the response:\n{"key": "value"}'
        result = strip_prose_preamble(text)
        assert 'Sure!' not in result
        assert '{"key": "value"}' in result
    
    def test_handles_clean_json(self):
        text = '{"key": "value"}'
        result = strip_prose_preamble(text)
        assert result.strip() == '{"key": "value"}'


class TestExtractJson:
    """Test JSON extraction from various formats."""
    
    def test_clean_json(self):
        text = '{"task_type": "analytical", "rationale": "test"}'
        result = extract_json(text)
        assert result["task_type"] == "analytical"
        assert result["rationale"] == "test"
    
    def test_json_with_markdown_fences(self):
        text = '```json\n{"task_type": "analytical"}\n```'
        result = extract_json(text)
        assert result["task_type"] == "analytical"
    
    def test_json_with_preamble(self):
        text = 'Here is the JSON:\n```json\n{"task_type": "analytical"}\n```'
        result = extract_json(text)
        assert result["task_type"] == "analytical"
    
    def test_json_with_perplexity_citations(self):
        text = '{"task_type": "analytical"} [1]\n\nSources:\n[1] https://example.com'
        result = extract_json(text)
        assert result["task_type"] == "analytical"
    
    def test_trailing_commas_removed(self):
        text = '{"items": [1, 2, 3,],}'
        result = extract_json(text)
        assert result["items"] == [1, 2, 3]
    
    def test_invalid_json_raises_error(self):
        text = 'This is not JSON at all'
        with pytest.raises(ParseError):
            extract_json(text)
    
    def test_empty_string_returns_empty_dict(self):
        """Empty LLM responses should gracefully fallback to empty dict."""
        assert extract_json("") == {}
        assert extract_json("   ") == {}
        assert extract_json("\n\t  \n") == {}

    def test_rejects_non_dict_json(self):
        """JSON arrays or strings must not be returned as dicts — raise ParseError instead.

        BUG: LLMs occasionally return bare JSON arrays like `["item1", "item2"]`
        or quoted strings like `"hello"`.  extract_json used to return these
        directly, causing downstream `.get()` to raise AttributeError on str/list.
        """
        # A bare array is wrapped rather than rejected — callers still get a dict,
        # which is what this regression is really about.
        assert extract_json('["item1", "item2"]') == {"results": ["item1", "item2"]}
        assert extract_json('```json\n["a", "b"]\n```') == {"results": ["a", "b"]}

        # Anything that is neither object nor array still raises.
        with pytest.raises(ParseError):
            extract_json('"hello world"')
        with pytest.raises(ParseError):
            extract_json('42')

    def test_nested_object_inside_array_is_extracted(self):
        """If the text contains both an array and an object, the object wins."""
        text = 'Some preamble ["bad", 1] then {"good": 2} end'
        result = extract_json(text)
        assert result == {"good": 2}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
