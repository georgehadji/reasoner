"""Tests for the in-memory cache layer in api.py."""

import json

import pytest

from reasoner.api import _MEMORY_CACHE, CACHE_DIR, _load_cache, _save_cache


def clear_memory_and_disk():
    _MEMORY_CACHE.clear()
    for f in CACHE_DIR.glob("test-mem-*.json"):
        try:
            f.unlink()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def cleanup():
    clear_memory_and_disk()
    yield
    clear_memory_and_disk()


@pytest.mark.asyncio
async def test_memory_cache_returns_data_without_disk_read():
    key = "test-mem-001"
    events = [{"type": "start"}, {"type": "done"}]

    # Seed memory directly; a memory hit is only honoured while the disk file
    # exists (another worker's erase deletes it), so the file must be there too.
    _MEMORY_CACHE[key] = events
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(["on-disk"]), encoding="utf-8")

    result = await _load_cache(key)
    assert result == events


@pytest.mark.asyncio
async def test_memory_hit_is_dropped_when_another_worker_erased_the_file():
    key = "test-mem-erased"
    await _save_cache(key, [{"type": "done"}])
    (CACHE_DIR / f"{key}.json").unlink()  # what erase_owner_cache does in a sibling worker

    assert await _load_cache(key) is None
    assert key not in _MEMORY_CACHE


@pytest.mark.asyncio
async def test_prune_runs_every_n_saves_and_tolerates_vanishing_files(monkeypatch):
    import reasoner.api.cache as cache

    calls: list[int] = []
    monkeypatch.setattr(cache, "_prune_disk_cache", lambda: calls.append(1))
    monkeypatch.setattr(cache, "_PRUNE_EVERY_SAVES", 3)
    monkeypatch.setattr(cache, "_saves_since_prune", 0)
    for i in range(7):
        await _save_cache(f"test-mem-prune-{i}", [])
    assert len(calls) == 2

    monkeypatch.undo()
    real_stat = type(CACHE_DIR / "x").stat

    def flaky(self, *a, **k):
        if self.name == "test-mem-prune-0.json":
            raise FileNotFoundError(self)
        return real_stat(self, *a, **k)

    monkeypatch.setattr(type(CACHE_DIR / "x"), "stat", flaky)
    cache._prune_disk_cache()  # must not raise


@pytest.mark.asyncio
async def test_save_cache_populates_memory():
    key = "test-mem-002"
    events = [{"type": "phase_complete", "data": {"solution": "hi"}}]

    await _save_cache(key, events)

    assert _MEMORY_CACHE.get(key) == events
    # Disk should also have it
    path = CACHE_DIR / f"{key}.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == events


@pytest.mark.asyncio
async def test_memory_cache_eviction():
    original_max = 256
    # Temporarily monkey-patch max size for fast test
    import reasoner.api as api_module
    api_module._MEMORY_CACHE_MAX_SIZE = 2
    try:
        api_module._MEMORY_CACHE.clear()
        await _save_cache("test-mem-a", [{"type": "a"}])
        await _save_cache("test-mem-b", [{"type": "b"}])
        await _save_cache("test-mem-c", [{"type": "c"}])

        assert len(api_module._MEMORY_CACHE) == 2
        assert "test-mem-a" not in api_module._MEMORY_CACHE
    finally:
        api_module._MEMORY_CACHE_MAX_SIZE = original_max
        api_module._MEMORY_CACHE.clear()
