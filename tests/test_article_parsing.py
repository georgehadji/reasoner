"""
Property tests for article pipeline parsing utilities (Phase 0).

Tests cover the pure, IO-free functions in article_phases.py and the
prompt builders in phases/article.py.  These are the unit-testable core
that the "functional core / imperative shell" (§2.1) depends on.

Pure functions under test:
  - _parse_sonar_citations()      — inline citation extraction
  - _extract_source_metadata()    — structured metadata extraction
"""

from __future__ import annotations

from reasoner.application.flows.article_phases import (
    _extract_source_metadata,
    _parse_sonar_citations,
)

# ═════════════════════════════════════════════════════════════════════
# _parse_sonar_citations
# ═════════════════════════════════════════════════════════════════════

class TestParseSonarCitations:
    """Property tests for the inline citation parser used by Sonar/Perplexity."""

    def test_standard_markdown_links(self):
        """Standard [Title](URL) format is parsed correctly."""
        text = (
            "According to recent research [Climate Report](https://climate.org/report), "
            "global temperatures are rising. "
            "See also [IPCC Analysis](https://ipcc.ch/2025/assessment)."
        )
        result = _parse_sonar_citations(text)
        assert len(result) == 2
        assert any(s["title"] == "Climate Report" for s in result)
        assert any(s["title"] == "IPCC Analysis" for s in result)
        assert all(s["url"].startswith("http") for s in result)

    def test_links_with_special_chars(self):
        """URLs with special characters are handled correctly."""
        text = (
            "[Study Results](https://doi.org/10.1000/xyz123?query=test&page=1) "
            "[Paper](https://arxiv.org/abs/2301.12345?context=cs.AI)"
        )
        result = _parse_sonar_citations(text)
        assert len(result) == 2
        assert all(s["url"] for s in result)

    def test_no_links(self):
        """Plain text with no links returns empty list."""
        result = _parse_sonar_citations("This is plain text with no links whatsoever.")
        assert result == []

    def test_only_valid_links(self):
        """Only http/https URLs are extracted."""
        text = "[Click here](https://valid.com) [Ignore](ftp://invalid.com) [Skip](mailto:test@test.com)"
        result = _parse_sonar_citations(text)
        assert len(result) == 1
        assert result[0]["url"] == "https://valid.com"

    def test_duplicate_urls_deduplicated(self):
        """Duplicate URLs are removed regardless of title."""
        text = (
            "[First](https://example.com/article) "
            "[Same URL](https://example.com/article)"
        )
        result = _parse_sonar_citations(text)
        assert len(result) == 1

    def test_bare_url_fallback(self):
        """When no markdown links exist, bare URLs are extracted as fallback."""
        text = "Check https://example.com/report for details and https://other.org/data"
        result = _parse_sonar_citations(text)
        assert len(result) == 2
        assert all(s["title"] for s in result)  # domain-derived title
        assert all(s["url"].startswith("http") for s in result)

    def test_bare_urls_ignored_when_markdown_links_present(self):
        """Bare URLs are NOT extracted when markdown links exist (prefer markdown)."""
        text = ("[Official Site](https://official.gov) has the data. "
                "Also see https://bare-url.com")
        result = _parse_sonar_citations(text)
        assert len(result) == 1
        assert result[0]["title"] == "Official Site"

    def test_trailing_punctuation_removed(self):
        """Trailing punctuation on URLs is stripped."""
        text = "[Link](https://example.com/page), [Other](https://test.com/)."
        result = _parse_sonar_citations(text)
        for s in result:
            assert not s["url"].endswith((",", ".", ";", ":")), f"URL '{s['url']}' has trailing punctuation"

    def test_multiline_markdown(self):
        """Links spanning multiple lines are parsed correctly."""
        text = """Multiple sources:
        - [First Source](https://first.com/info)
        - [Second Source](https://second.com/data)
        - [Third Source](https://third.com/report)
        See also the appendix."""
        result = _parse_sonar_citations(text)
        assert len(result) == 3

    def test_empty_and_edge_cases(self):
        """Edge cases: empty input, very short text, whitespace-only."""
        assert _parse_sonar_citations("") == []
        assert _parse_sonar_citations("   ") == []
        assert _parse_sonar_citations("A short sentence.") == []
        assert _parse_sonar_citations("[Broken") == []

    def test_urls_with_parens(self):
        """URLs containing parentheses are handled (common in Wikipedia-style URLs)."""
        text = "[Article](https://en.wikipedia.org/wiki/Climate_change_(disambiguation))"
        result = _parse_sonar_citations(text)
        assert len(result) == 1
        assert "disambiguation" in result[0]["url"]

    def test_long_text_with_mixed_formats(self):
        """Realistic long-form text with mixed formats is handled gracefully."""
        text = """
        According to the latest IPCC report [Climate Science 2025](https://ipcc.ch/report), 
        we need immediate action. The data from [NOAA](https://noaa.gov/climate) confirms this.
        
        However, critics at https://skeptical-site.com argue otherwise — though their methods
        are questionable. The authoritative source is https://science.org/consensus.
        
        For a comprehensive overview, see [Nature Study](https://nature.com/articles/climate2025),
        which reviews all recent findings.
        """
        result = _parse_sonar_citations(text)
        # Should have exactly 3 markdown links (bare URLs ignored when markdown present)
        assert len(result) == 3
        titles = {s["title"] for s in result}
        assert "Climate Science 2025" in titles
        assert "NOAA" in titles
        assert "Nature Study" in titles


# ═════════════════════════════════════════════════════════════════════
# _extract_source_metadata
# ═════════════════════════════════════════════════════════════════════

class TestExtractSourceMetadata:
    """Property tests for source metadata extraction."""

    def test_full_metadata(self):
        """All fields are extracted correctly."""
        sources = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "author": "Jane Doe",
                "date": "2025-01-15",
                "publisher": "Test Publisher",
                "snippet": "This is a snippet of the article content that is quite informative.",
            }
        ]
        result = _extract_source_metadata(sources)
        assert len(result) == 1
        meta = result[0]
        assert meta["title"] == "Test Article"
        assert meta["url"] == "https://example.com/article"
        assert meta["author"] == "Jane Doe"
        assert meta["date"] == "2025-01-15"
        assert meta["publisher"] == "Test Publisher"
        assert meta["snippet"] == "This is a snippet of the article content that is quite informative."

    def test_missing_fields_default_to_empty_string(self):
        """Fields missing from source dict are filled with empty strings."""
        sources = [{"title": "Minimal"}]
        result = _extract_source_metadata(sources)
        assert len(result) == 1
        meta = result[0]
        assert meta["title"] == "Minimal"
        assert meta["url"] == ""
        assert meta["author"] == ""
        assert meta["date"] == ""
        assert meta["publisher"] == ""

    def test_empty_input_returns_empty(self):
        """Empty source list returns empty list."""
        assert _extract_source_metadata([]) == []

    def test_snippet_truncated(self):
        """Snippets over 500 chars are truncated."""
        long_snippet = "X" * 1000
        sources = [{"snippet": long_snippet}]
        result = _extract_source_metadata(sources)
        assert len(result[0]["snippet"]) == 500

    def test_numeric_values_str(self):
        """Non-string values for title/author are converted to string."""
        sources = [{"title": 123, "url": None, "date": 20250115}]
        result = _extract_source_metadata(sources)
        assert isinstance(result[0]["title"], str)
        assert isinstance(result[0]["date"], str)

    def test_multiple_sources(self):
        """Multiple sources each get their own metadata entry."""
        sources = [
            {"title": "A", "url": "https://a.com"},
            {"title": "B", "url": "https://b.com"},
        ]
        result = _extract_source_metadata(sources)
        assert len(result) == 2

    def test_realistic_search_results(self):
        """Realistic search result format is handled."""
        sources = [
            {
                "title": "Quantum Computing Breakthrough",
                "url": "https://nature.com/articles/quantum-2025",
                "author": "Smith et al.",
                "date": "2025-03-20",
                "publisher": "Nature",
                "snippet": "Researchers demonstrate a 1000-qubit quantum processor with error correction...",
            },
            {
                "title": "Quantum Computing: A Review",
                "url": "https://arxiv.org/abs/2503.12345",
                "author": "",
                "date": "",
                "publisher": "arXiv",
                "snippet": "Comprehensive review of recent advances in quantum computing...",
            },
        ]
        result = _extract_source_metadata(sources)
        assert len(result) == 2
        assert result[0]["author"] == "Smith et al."
        assert result[1]["author"] == ""  # missing preserved as empty
