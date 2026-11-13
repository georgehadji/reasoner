"""Tests for the DELETE /api/cache endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

import reasoner.api.cache as cache_module
from reasoner.api import _MEMORY_CACHE, _save_cache, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup(tmp_path, monkeypatch):
    # A private cache dir per test: clear_cache also counts per-owner
    # u-*/*.json files, which other tests leave in the shared CACHE_DIR.
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    _MEMORY_CACHE.clear()
    yield
    _MEMORY_CACHE.clear()


class TestClearCacheEndpoint:
    """Verify clear_cache invalidates both disk and memory layers."""

    def test_clear_cache_empty_returns_zero(self):
        response = client.delete("/api/cache")
        assert response.status_code == 200
        data = response.json()
        assert data["cleared"] == 0
        assert len(_MEMORY_CACHE) == 0

    def test_clear_cache_deletes_disk_files(self):
        # Seed disk with a synthetic cache file
        key = "test-clear-001"
        path = cache_module.CACHE_DIR / f"{key}.json"
        path.write_text(json.dumps([{"type": "done"}]), encoding="utf-8")

        response = client.delete("/api/cache")
        assert response.status_code == 200
        assert response.json()["cleared"] >= 1
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_clear_cache_clears_memory_cache(self):
        key = "test-clear-002"
        await _save_cache(key, [{"type": "start"}, {"type": "done"}])
        assert key in _MEMORY_CACHE

        response = client.delete("/api/cache")
        assert response.status_code == 200
        assert len(_MEMORY_CACHE) == 0
        assert key not in _MEMORY_CACHE

    @pytest.mark.asyncio
    async def test_clear_cache_subsequent_requests_miss(self):
        key = "test-clear-003"
        await _save_cache(key, [{"type": "done", "solution": "cached"}])

        # Clear
        client.delete("/api/cache")

        # Load should miss
        from reasoner.api.cache import _load_cache
        result = await _load_cache(key)
        assert result is None
