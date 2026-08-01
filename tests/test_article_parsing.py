"""
Property tests for article pipeline parsing utilities (Phase 0).

Pure functions under test:
  - _parse_sonar_citations()  — inline citation extraction
  - _extract_source_metadata() — structured metadata extraction
"""

from __future__ import annotations

import pytest

from reasoner.application.flows.article_phases import (
    _parse_sonar_citations,
    _extract_source_metadata,
)


class TestParseSonarCitations:

    def test_standard_markdown_links(self):
        result = _parse_sonar_citations(
            "[Climate Report](https://climate.org/report) [IPCC Analysis](https://ipcc.ch/2025/assessment)"
        )
        assert len(result) == 2
        assert any(s["title"] == "Climate Report" for s in result)
        assert any(s["title"] == "IPCC Analysis" for s in result)
        assert all(s["url"].startswith("http") for s in result)

    def test_links_with_special_chars(self):
        result = _parse_sonar_citations(
            "[Study](https://doi.org/10.1000/xyz123?query=test) [Paper](https://arxiv.org/abs/2301.12345?context=cs.AI)"
        )
        assert len(result) == 2
        assert all(s["url"] for s in result)

    def test_no_links(self):
        assert _parse_sonar_citations("Plain text with no links") == []

    def test_only_http_links(self):
        result = _parse_sonar_citations("[Valid](https://valid.com) [Ignore](ftp://invalid.com)")
        assert len(result) == 1
        assert result[0]["url"] == "https://valid.com"

    def test_duplicate_urls_deduplicated(self):
        result = _parse_sonar_citations("[First](https://x.com) [Same](https://x.com)")
        assert len(result) == 1

    def test_bare_url_fallback(self):
        result = _parse_sonar_citations("Check https://a.com/report and https://b.org/data")
        assert len(result) == 2
        assert all(s["url"].startswith("http") for s in result)

    def test_empty_and_whitespace(self):
        assert _parse_sonar_citations("") == []
        assert _parse_sonar_citations("   ") == []

    def test_urls_with_parentheses(self):
        result = _parse_sonar_citations(
            "[Article](https://en.wikipedia.org/wiki/Climate_change_(disambiguation))"
        )
        assert len(result) == 1
        assert "disambiguation" in result[0]["url"]


class TestExtractSourceMetadata:

    def test_full_metadata(self):
        sources = [{"title": "Test", "url": "https://t.com", "author": "Jane", "date": "2025-01-01", "publisher": "Pub", "snippet": "Content here."}]
        result = _extract_source_metadata(sources)
        assert len(result) == 1
        m = result[0]
        assert m["title"] == "Test"
        assert m["url"] == "https://t.com"
        assert m["author"] == "Jane"
        assert m["date"] == "2025-01-01"
        assert m["publisher"] == "Pub"

    def test_missing_fields_default_to_empty(self):
        result = _extract_source_metadata([{"title": "Minimal"}])
        assert result[0]["url"] == ""
        assert result[0]["author"] == ""
        assert result[0]["date"] == ""

    def test_empty_input(self):
        assert _extract_source_metadata([]) == []

    def test_snippet_truncated(self):
        result = _extract_source_metadata([{"snippet": "X" * 1000}])
        assert len(result[0]["snippet"]) == 500

    def test_multiple_sources(self):
        sources = [{"title": "A"}, {"title": "B"}]
        assert len(_extract_source_metadata(sources)) == 2
