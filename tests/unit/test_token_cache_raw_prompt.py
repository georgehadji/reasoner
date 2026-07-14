"""Round-trip test: raw_prompt must survive disk serialization.

Regression guard for B-04: _save_to_disk previously omitted raw_prompt,
causing Jaccard similarity to always return 0.0 after a cache reload.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from reasoner.infrastructure.token_cache import CacheEntry, TokenAwareCache


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _make_entry(key: str, raw_prompt: str) -> CacheEntry:
    return CacheEntry(
        key=key,
        problem_hash="testhash",
        phase="test_phase",
        model_id="test-model",
        prompt_hash="prompthash",
        response="test response",
        tokens_used=10,
        created_at=time.time(),
        ttl_seconds=3600,
        raw_prompt=raw_prompt,
    )


@pytest.mark.asyncio
async def test_raw_prompt_survives_disk_round_trip(tmp_cache_dir: Path) -> None:
    cache1 = TokenAwareCache(cache_dir=tmp_cache_dir)
    entry = _make_entry("key1", "what is the capital of france")
    await cache1._save_to_disk("key1", entry)

    # Load via a fresh cache instance (simulates restart)
    cache2 = TokenAwareCache(cache_dir=tmp_cache_dir)
    await cache2._load_from_disk()

    loaded = cache2._entries.get("key1")
    assert loaded is not None, "Entry not found after disk reload"
    assert loaded.raw_prompt == "what is the capital of france", (
        f"raw_prompt not persisted: got {loaded.raw_prompt!r}"
    )
