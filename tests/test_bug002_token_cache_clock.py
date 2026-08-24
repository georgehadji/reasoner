"""
Regression tests for BUG-002: Token cache monotonic clock cross-session.

Verifies that the cache uses wall-clock time (time.time()) instead of
monotonic time (time.monotonic()) for values that get persisted to disk
and loaded in a new process.

Bug: created_at was stored as time.monotonic(), which is per-process.
On disk reload in a new process, TTL checks compared the new process's
monotonic clock against the old process's value — producing meaningless
results. Stale entries could persist indefinitely, or fresh entries be
immediately evicted.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from reasoner.token_cache import TokenAwareCache


class TestBug002TokenCacheClock:

    @pytest.mark.asyncio
    async def test_created_at_is_wall_clock(self, tmp_path: Path):
        """
        Verify that created_at is stored as wall-clock time (time.time()),
        not monotonic time.

        Before: time.monotonic() — cannot be compared across processes.
        After:  time.time() — absolute epoch seconds, comparable everywhere.
        """
        cache = TokenAwareCache(cache_dir=tmp_path / "wall_check")

        before = time.time()
        await cache.set(
            problem="p", phase="ph", model_id="m",
            prompt="pr", response="r", tokens_used=5,
        )
        after = time.time()

        # Verify created_at is between before and after (wall-clock behavior)
        key = cache._compute_key("p", "ph", "m", "pr")
        entry = cache._entries[key]

        assert before <= entry.created_at <= after, (
            f"created_at ({entry.created_at}) should be between wall-clock "
            f"times {before} and {after}"
        )

    @pytest.mark.asyncio
    async def test_ttl_survives_disk_reload(self, tmp_path: Path):
        """
        BUG-002 regression: An entry saved to disk and then loaded by a fresh
        cache instance (simulating process restart) must have correct TTL.

        Without fix: monotonic timestamps from old process produce meaningless
        TTL comparisons in the new process → TTL either always expired or never.
        With fix: wall-clock timestamps produce correct TTL regardless of process.
        """
        cache_dir = tmp_path / "ttl_reload"

        # First cache instance — store an entry
        cache1 = TokenAwareCache(
            max_tokens=1_000_000,
            ttl_seconds=3600,
            cache_dir=cache_dir,
        )
        await cache1.set(
            problem="test problem",
            phase="test",
            model_id="test-model",
            prompt="test prompt",
            response="cached response",
            tokens_used=10,
        )
        key = cache1._compute_key("test problem", "test", "test-model", "test prompt")

        # Verify disk file exists with wall-clock created_at
        disk_file = cache_dir / f"{key}.json"
        assert disk_file.exists(), "Cache file should exist on disk"
        raw = json.loads(disk_file.read_text())
        assert "created_at" in raw, "created_at must be serialized to disk"

        # Second cache instance — simulate process restart (fresh object)
        cache2 = TokenAwareCache(
            max_tokens=1_000_000,
            ttl_seconds=3600,
            cache_dir=cache_dir,
        )

        # The entry should survive the reload (TTL well within 3600s window)
        result = await cache2.get(
            problem="test problem",
            phase="test",
            model_id="test-model",
            prompt="test prompt",
        )
        assert result == "cached response", (
            "Cache entry must survive disk reload within TTL window. "
            "If this fails, the clock type fix may not be working."
        )

    @pytest.mark.asyncio
    async def test_entry_expires_after_ttl_on_reload(self, tmp_path: Path):
        """
        Verify that entries with expired TTL are evicted on disk reload.
        Use a very short TTL and force time past it.
        """
        cache_dir = tmp_path / "ttl_expiry"
        short_ttl = 1  # 1 second

        cache1 = TokenAwareCache(
            max_tokens=1_000_000,
            ttl_seconds=short_ttl,
            cache_dir=cache_dir,
        )
        await cache1.set(
            problem="will expire",
            phase="test",
            model_id="m",
            prompt="prompt",
            response="ephemeral",
            tokens_used=5,
        )

        # Wait past TTL
        await asyncio.sleep(1.5)

        # New process load — entry should be expired
        cache2 = TokenAwareCache(
            max_tokens=1_000_000,
            ttl_seconds=short_ttl,
            cache_dir=cache_dir,
        )
        result = await cache2.get(
            problem="will expire",
            phase="test",
            model_id="m",
            prompt="prompt",
        )
        assert result is None, (
            "Expired entry should not survive disk reload. "
            "If result != None, TTL check may still use monotonic time."
        )

    @pytest.mark.asyncio
    async def test_last_accessed_is_wall_clock(self, tmp_path: Path):
        """
        Verify that last_accessed is updated with wall-clock time on cache hits.
        """
        cache_dir = tmp_path / "last_access"
        cache = TokenAwareCache(cache_dir=cache_dir)

        await cache.set(
            problem="p", phase="ph", model_id="m",
            prompt="pr", response="r", tokens_used=5,
        )

        # Hit the cache
        before_access = time.time()
        result = await cache.get("p", "ph", "m", "pr")
        after_access = time.time()

        assert result == "r"

        key = cache._compute_key("p", "ph", "m", "pr")
        entry = cache._entries[key]
        assert before_access <= entry.last_accessed <= after_access, (
            f"last_accessed ({entry.last_accessed}) should be between "
            f"{before_access} and {after_access}"
        )

    @pytest.mark.asyncio
    async def test_disk_serialization_roundtrip(self, tmp_path: Path):
        """
        Verify that created_at and last_accessed round-trip correctly
        through JSON serialization and deserialization.
        """
        cache_dir = tmp_path / "roundtrip"
        cache = TokenAwareCache(cache_dir=cache_dir)

        await cache.set(
            problem="roundtrip test",
            phase="ph1",
            model_id="m1",
            prompt="prompt text",
            response="response text",
            tokens_used=100,
        )

        key = cache._compute_key("roundtrip test", "ph1", "m1", "prompt text")
        disk_file = cache_dir / f"{key}.json"

        assert disk_file.exists()
        raw = json.loads(disk_file.read_text())

        # Both timestamps must be valid floats
        assert isinstance(raw["created_at"], (int, float)), (
            f"created_at must be numeric, got {type(raw['created_at'])}"
        )
        assert isinstance(raw["last_accessed"], (int, float)), (
            f"last_accessed must be numeric, got {type(raw['last_accessed'])}"
        )

        # They should be positive (epoch-based)
        assert raw["created_at"] > 1_000_000_000, (
            f"created_at ({raw['created_at']}) seems too small for epoch time"
        )
        assert raw["last_accessed"] > 1_000_000_000, (
            f"last_accessed ({raw['last_accessed']}) seems too small for epoch time"
        )

    @pytest.mark.asyncio
    async def test_in_process_ttl_expires(self, tmp_path: Path):
        """
        Even without disk reload, ensure that in-process TTL expiration works.
        """
        cache = TokenAwareCache(
            max_tokens=1_000_000,
            ttl_seconds=1,
        )

        await cache.set(
            problem="in-process ttl",
            phase="test",
            model_id="m",
            prompt="prompt",
            response="will expire",
            tokens_used=5,
        )

        # Immediately accessible
        result = await cache.get("in-process ttl", "test", "m", "prompt")
        assert result == "will expire"

        # Wait past TTL
        await asyncio.sleep(1.5)

        # Now expired
        result = await cache.get("in-process ttl", "test", "m", "prompt")
        assert result is None, (
            "In-process TTL should evict expired entries. "
            f"Got {result!r}, expected None"
        )



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
