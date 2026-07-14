"""Regression tests for token cache counter leak on overwrite."""
from __future__ import annotations

import pytest

from reasoner.token_cache import TokenAwareCache


@pytest.mark.asyncio
async def test_set_overwrite_does_not_leak_tokens():
    """
    BUG-007: Overwriting an existing cache key must subtract the old entry's
    token count before adding the new one. Without this fix, _current_tokens
    grows monotonically until it exceeds max_tokens, causing degenerate LRU
    eviction on every subsequent write.
    """
    cache = TokenAwareCache(
        max_tokens=100,
        max_entries=10,
        ttl_seconds=60,
        cache_dir=None,
    )

    # Prime the cache with a 40-token entry
    await cache.set(
        problem="What is 2+2?",
        phase="test",
        model_id="test-model",
        prompt="Solve 2+2",
        response="4",
        tokens_used=40,
    )
    assert cache._current_tokens == 40

    # Overwrite the same key with a 30-token entry
    await cache.set(
        problem="What is 2+2?",
        phase="test",
        model_id="test-model",
        prompt="Solve 2+2",
        response="The answer is four.",
        tokens_used=30,
    )

    # After fix: 40 - 40 + 30 = 30
    # Before fix: 40 + 30 = 70 (leak)
    assert cache._current_tokens == 30, (
        f"Token counter leaked: expected 30, got {cache._current_tokens}. "
        f"Old entry's tokens were not subtracted on overwrite."
    )


@pytest.mark.asyncio
async def test_set_overwrite_same_tokens_stable():
    """Overwriting with identical tokens should keep counter stable."""
    cache = TokenAwareCache(
        max_tokens=100,
        max_entries=10,
        ttl_seconds=60,
        cache_dir=None,
    )

    await cache.set(
        problem="Q",
        phase="p",
        model_id="m",
        prompt="p",
        response="A",
        tokens_used=25,
    )
    assert cache._current_tokens == 25

    await cache.set(
        problem="Q",
        phase="p",
        model_id="m",
        prompt="p",
        response="A2",
        tokens_used=25,
    )
    assert cache._current_tokens == 25


@pytest.mark.asyncio
async def test_set_overwrite_larger_entry():
    """Overwriting with a larger entry should correctly account for growth."""
    cache = TokenAwareCache(
        max_tokens=100,
        max_entries=10,
        ttl_seconds=60,
        cache_dir=None,
    )

    await cache.set(
        problem="Q",
        phase="p",
        model_id="m",
        prompt="p",
        response="A",
        tokens_used=20,
    )
    assert cache._current_tokens == 20

    await cache.set(
        problem="Q",
        phase="p",
        model_id="m",
        prompt="p",
        response="A much longer response",
        tokens_used=50,
    )
    assert cache._current_tokens == 50
