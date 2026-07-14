"""Tests for the in-memory cache layer in api.py."""

import json
import pytest
from reasoner.api import _load_cache, _save_cache, _MEMORY_CACHE, CACHE_DIR


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

    # Seed memory directly
    _MEMORY_CACHE[key] = events

    result = await _load_cache(key)
    assert result == events


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
