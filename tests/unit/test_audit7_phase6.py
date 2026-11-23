"""Audit 7, phase 6: the token cache's eviction, disk cap and at-rest encryption."""

from __future__ import annotations

import json
import os

import pytest

from reasoner.infrastructure.token_cache import TokenAwareCache


def _files(cache_dir):
    return list(cache_dir.glob("*.json"))


@pytest.mark.asyncio
async def test_600_entries_leave_512_in_memory_and_512_files(tmp_path):
    cache = TokenAwareCache(cache_dir=tmp_path)
    for i in range(600):
        await cache.set(f"p{i}", "phase", "m", f"prompt {i}", f"answer {i}", 1)
    assert len(cache._entries) == 512
    assert len(_files(tmp_path)) == 512


@pytest.mark.asyncio
async def test_restart_with_a_backlog_loads_the_newest_512_and_deletes_the_rest(tmp_path):
    for i in range(2000):
        f = tmp_path / f"{i:032d}.json"
        f.write_text(json.dumps({
            "key": f"{i:032d}", "problem_hash": f"h{i}", "phase": "p", "model_id": "m",
            "prompt_hash": "x", "response": "r", "tokens_used": 1,
            "created_at": 10**10, "ttl_seconds": 10**10,
        }))
        os.utime(f, (1_000_000 + i, 1_000_000 + i))  # file i is newer than file i-1
    cache = TokenAwareCache(cache_dir=tmp_path)
    await cache._ensure_loaded()
    assert len(cache._entries) == 512
    assert len(_files(tmp_path)) == 512
    assert set(cache._entries) == {f"{i:032d}" for i in range(1488, 2000)}


@pytest.mark.asyncio
async def test_eviction_is_least_recently_used_and_removes_the_file(tmp_path):
    cache = TokenAwareCache(cache_dir=tmp_path)
    cache._lru_max_entries = 3
    for name in "abc":
        await cache.set(name, "phase", "m", name, name, 1)
    key_b = cache._compute_key("b", "phase", "m", "b")
    assert (tmp_path / f"{key_b}.json").exists()
    assert await cache.get("a", "phase", "m", "a") == "a"  # promotes a
    await cache.set("d", "phase", "m", "d", "d", 1)
    assert await cache.get("b", "phase", "m", "b") is None
    assert await cache.get("a", "phase", "m", "a") == "a"
    assert not (tmp_path / f"{key_b}.json").exists()


@pytest.mark.asyncio
async def test_prompts_are_encrypted_on_disk_and_survive_a_reload(tmp_path):
    cache = TokenAwareCache(cache_dir=tmp_path)
    await cache.set("the problem", "phase", "m", "a secret prompt", "a secret answer", 5)
    (path,) = _files(tmp_path)
    text = path.read_text()
    assert "a secret prompt" not in text and "a secret answer" not in text
    assert "payload" in json.loads(text)

    reloaded = TokenAwareCache(cache_dir=tmp_path)
    assert await reloaded.get("the problem", "phase", "m", "a secret prompt") == "a secret answer"


@pytest.mark.asyncio
async def test_a_file_removed_by_another_worker_mid_load_is_skipped(tmp_path):
    cache = TokenAwareCache(cache_dir=tmp_path)
    await cache.set("kept", "phase", "m", "kept", "kept", 1)
    (real,) = _files(tmp_path)
    reloaded = TokenAwareCache(cache_dir=tmp_path)
    reloaded._files_newest_first = lambda: [tmp_path / "gone.json", real]

    await reloaded._ensure_loaded()

    assert reloaded._loaded and len(reloaded._entries) == 1


@pytest.mark.asyncio
async def test_an_encryption_setup_error_deletes_no_files(tmp_path, monkeypatch):
    import reasoner.security.encryption as encryption

    cache = TokenAwareCache(cache_dir=tmp_path)
    await cache.set("p", "phase", "m", "prompt", "answer", 1)

    def _broken():
        raise RuntimeError("no key configured")

    monkeypatch.setattr(encryption, "get_encryption_service", _broken)
    reloaded = TokenAwareCache(cache_dir=tmp_path)
    await reloaded._ensure_loaded()

    assert not reloaded._loaded and len(_files(tmp_path)) == 1
