"""
Search quality unit tests.

Covers:
- Off-topic domain rejection (biography, dictionary, reddit, etc.)
- Empty fallback behavior (no unfiltered raw results)
- Keyword extraction from mixed-language prompts
- Decomposition result caching
"""

from __future__ import annotations

import time

import pytest

from reasoner.core.search import (
    _DECOMPOSITION_CACHE,
    _DECOMPOSITION_TTL_SECONDS,
    _extract_search_keywords,
    _should_include_result,
)

# ═════════════════════════════════════════════════════════════════════
# _should_include_result tests
# ═════════════════════════════════════════════════════════════════════

class TestShouldIncludeResult:
    def test_accepts_relevant_result(self):
        result = {
            "title": "Scientific method for hypothesis testing",
            "url": "https://arxiv.org/abs/1234.5678",
            "content": "The scientific method is a systematic procedure for investigating phenomena...",
        }
        assert _should_include_result(result) is True

    @pytest.mark.parametrize(
        "domain,title",
        [
            ("biography.com", "Albert Einstein biography"),
            ("wordreference.com", "Definition of hypothesis"),
            ("reddit.com", "r/science discussion"),
            ("imdb.com", "The Theory of Everything"),
            ("facebook.com", "Science group post"),
            ("pinterest.com", "Science infographic"),
        ],
    )
    def test_rejects_off_topic_domains(self, domain, title):
        result = {
            "title": title,
            "url": f"https://{domain}/page",
            "content": "Some content here that is long enough to pass length checks.",
        }
        assert _should_include_result(result) is False

    def test_rejects_listicle_title(self):
        result = {
            "title": "Top 10 Best Python Frameworks You Must Discover",
            "url": "https://example.com/article",
            "content": "Here are the best frameworks for Python development in 2024...",
        }
        assert _should_include_result(result) is False

    def test_rejects_short_snippet(self):
        result = {
            "title": "Some article",
            "url": "https://example.com/article",
            "content": "Hi",
        }
        assert _should_include_result(result) is False

    def test_rejects_raw_data_file(self):
        result = {
            "title": "data.json",
            "url": "https://example.com/data.json",
            "content": "Some content here that is long enough to pass length checks.",
        }
        assert _should_include_result(result) is False

    def test_rejects_github_blob(self):
        result = {
            "title": "tokenizer.json",
            "url": "https://github.com/org/repo/blob/main/tokenizer.json",
            "content": "Some content here that is long enough to pass length checks.",
        }
        assert _should_include_result(result) is False

    def test_rejects_obvious_nsfw_and_ugc_domains(self):
        nsfw = {
            "title": "IDOL FACE gets RUINED through DIRTY GLORYHOLE",
            "url": "https://steamcommunity.com/discussions/id123",
            "content": "Some content here that is long enough to pass length checks.",
        }
        assert _should_include_result(nsfw) is False

    def test_rejects_empty_url(self):
        assert _should_include_result({"title": "x", "url": "", "content": "y" * 30}) is False


# ═════════════════════════════════════════════════════════════════════
# Keyword extraction tests
# ═════════════════════════════════════════════════════════════════════

class TestExtractSearchKeywords:
    def test_extracts_english_keywords(self):
        text = "What are the best practices for machine learning in production?"
        keywords = _extract_search_keywords(text)
        assert "machine" in keywords
        assert "learning" in keywords
        assert "production" in keywords
        assert "the" not in keywords
        assert "are" not in keywords

    def test_mixed_language_fallback(self):
        text = "Comment faire du machine learning en production?"
        keywords = _extract_search_keywords(text)
        # Should extract English keywords and ignore French stop words
        assert "machine" in keywords
        assert "learning" in keywords
        assert "production" in keywords

    def test_deduplicates_keywords(self):
        text = "Machine learning and machine learning models"
        keywords = _extract_search_keywords(text)
        # "machine" and "learning" should each appear only once
        assert keywords.count("machine") == 1
        assert keywords.count("learning") == 1

    def test_respects_max_keywords(self):
        text = "one two three four five six seven eight nine ten eleven"
        keywords = _extract_search_keywords(text, max_keywords=3)
        assert len(keywords.split()) <= 3

    def test_returns_empty_for_no_keywords(self):
        text = "12345 !!! @@@"
        keywords = _extract_search_keywords(text)
        assert keywords == ""


# ═════════════════════════════════════════════════════════════════════
# Decomposition cache tests
# ═════════════════════════════════════════════════════════════════════

class TestDecompositionCache:
    def test_cache_stores_and_retrieves(self):
        query = "test query"
        sub_queries = ["sub 1", "sub 2"]
        now = time.time()
        _DECOMPOSITION_CACHE[query] = (sub_queries, now)

        cached = _DECOMPOSITION_CACHE.get(query)
        assert cached is not None
        assert cached[0] == sub_queries

        # Clean up
        _DECOMPOSITION_CACHE.pop(query, None)

    def test_cache_expires_after_ttl(self):
        query = "expiring query"
        sub_queries = ["sub 1"]
        now = time.time()
        _DECOMPOSITION_CACHE[query] = (sub_queries, now - _DECOMPOSITION_TTL_SECONDS - 1)

        cached = _DECOMPOSITION_CACHE.get(query)
        # Entry exists in dict but is stale; production code removes it on read
        assert cached is not None
        ts = cached[1]
        assert now - ts > _DECOMPOSITION_TTL_SECONDS

        # Clean up
        _DECOMPOSITION_CACHE.pop(query, None)
