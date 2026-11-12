"""Tests for TokenAwareCache exact-match retrieval (no fuzzy hits)."""

from __future__ import annotations

import pytest

from reasoner.token_cache import TokenAwareCache


class TestSemanticGet:
    """Integration tests for cache retrieval."""

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
    async def test_near_miss_prompt_is_a_miss(self, cache):
        await cache.set(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="how to sort a list in python",
            response="Use the sorted() function or .sort() method...",
            tokens_used=100,
        )
        # Same problem, 7/8 words shared: still a different prompt, so a miss.
        result = await cache.get(
            problem="Explain quantum computing",
            phase="synthesis",
            model_id="gpt-4o",
            prompt="how to sort a list in python language",
        )
        assert result is None

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
