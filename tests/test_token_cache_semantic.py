"""Tests for TokenAwareCache semantic (Jaccard) matching."""

from __future__ import annotations

import pytest

from reasoner.token_cache import TokenAwareCache


class TestJaccardSimilarity:
    """Unit tests for the static Jaccard helper."""

    def test_identical_texts(self):
        assert TokenAwareCache._jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert TokenAwareCache._jaccard_similarity("abc def", "xyz uvw") == 0.0

    def test_partial_overlap(self):
        # hello world foo bar -> 4 unique words
        # set A = {hello, world, foo}, set B = {hello, world, bar}
        # intersection = 2, union = 4 -> 2/4 = 0.5
        sim = TokenAwareCache._jaccard_similarity("hello world foo", "hello world bar")
        assert sim == pytest.approx(0.5, rel=1e-3)

    def test_empty_texts(self):
        assert TokenAwareCache._jaccard_similarity("", "hello") == 0.0
        assert TokenAwareCache._jaccard_similarity("hello", "") == 0.0

    def test_case_insensitive(self):
        assert TokenAwareCache._jaccard_similarity("Hello World", "hello world") == 1.0


class TestSemanticGet:
    """Integration tests for semantic cache retrieval."""

    @pytest.fixture
    def cache(self):
        c = TokenAwareCache(max_tokens=10_000, ttl_seconds=3600)
        return c

    @pytest.mark.asyncio
    async def test_exact_match_still_works(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
            response="Quantum computing uses qubits...",
            tokens_used=100,
        )
        result = await cache.get(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
        )
        assert result == "Quantum computing uses qubits..."

    @pytest.mark.asyncio
    async def test_semantic_near_miss(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="how to sort a list in python",
            response="Use the sorted() function or .sort() method...",
            tokens_used=100,
        )
        # Same problem, very similar prompt -> Jaccard > 0.85
        # "how to sort a list in python language" shares 7/8 words -> Jaccard = 0.875
        result = await cache.get(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="how to sort a list in python language",
        )
        assert result == "Use the sorted() function or .sort() method..."

    @pytest.mark.asyncio
    async def test_semantic_miss_different_problem(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
            response="Quantum computing uses qubits...",
            tokens_used=100,
        )
        # Different problem -> different problem_hash -> no match
        result = await cache.get(
            problem="Explain classical computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_miss_different_phase(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
            response="Quantum computing uses qubits...",
            tokens_used=100,
        )
        result = await cache.get(
            problem="Explain quantum computing",
            phase="classification",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_miss_below_threshold(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
            response="Quantum computing uses qubits...",
            tokens_used=100,
        )
        # Very different prompt -> Jaccard < 0.85
        result = await cache.get(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="How do I bake sourdough bread?",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_threshold(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing?",
            response="Quantum computing uses qubits...",
            tokens_used=100,
        )
        # With threshold=1.0, only exact match works
        result = await cache.get(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="What is quantum computing exactly?",
            semantic_threshold=1.0,
        )
        assert result is None
