"""Tests for the DELETE /api/cache endpoint."""

import json
import pytest
from fastapi.testclient import TestClient

from reasoner.api import _MEMORY_CACHE, _save_cache, CACHE_DIR, app
from reasoner.core.settings import Settings


client = TestClient(app)

ADMIN_KEY = "test-admin-key-for-cache-clear"
AUTH = {"X-Admin-Key": ADMIN_KEY}


@pytest.fixture(autouse=True)
def _admin_key(monkeypatch):
    """DELETE /api/cache is admin-only — a CSRF token alone used to be enough,
    and a CSRF token is freely mintable, so any caller could wipe the cache.

    Patch the CLASS, not the `settings` instance. monkeypatch.undo() restores by
    setattr, so patching the instance leaves a permanent instance attribute that
    shadows the class attribute for the rest of the session — silently breaking
    any later test that patches Settings.ADMIN_API_KEY (test_feedback.py does).
    """
    monkeypatch.setattr(Settings, "ADMIN_API_KEY", ADMIN_KEY)


def clear_memory_and_disk():
    _MEMORY_CACHE.clear()
    for f in CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def cleanup():
    clear_memory_and_disk()
    yield
    clear_memory_and_disk()


class TestClearCacheEndpoint:
    """Verify clear_cache invalidates both disk and memory layers."""

    def test_clear_cache_empty_returns_zero(self):
        response = client.delete("/api/cache", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["cleared"] == 0
        assert len(_MEMORY_CACHE) == 0

    def test_clear_cache_deletes_disk_files(self):
        # Seed disk with a synthetic cache file
        key = "test-clear-001"
        path = CACHE_DIR / f"{key}.json"
        path.write_text(json.dumps([{"type": "done"}]), encoding="utf-8")

        response = client.delete("/api/cache", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["cleared"] >= 1
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_clear_cache_clears_memory_cache(self):
        key = "test-clear-002"
        await _save_cache(key, [{"type": "start"}, {"type": "done"}])
        assert key in _MEMORY_CACHE

        response = client.delete("/api/cache", headers=AUTH)
        assert response.status_code == 200
        assert len(_MEMORY_CACHE) == 0
        assert key not in _MEMORY_CACHE

    @pytest.mark.asyncio
    async def test_clear_cache_subsequent_requests_miss(self):
        key = "test-clear-003"
        await _save_cache(key, [{"type": "done", "solution": "cached"}])

        # Clear
        client.delete("/api/cache", headers=AUTH)

        # Load should miss
        from reasoner.api.cache import _load_cache
        result = await _load_cache(key)
        assert result is None

    # ── Authorization ──────────────────────────────────────────────────────
    # These live in this class rather than their own so that pytest-xdist's
    # --dist loadscope keeps them on the same worker. Split across workers,
    # the module's autouse cleanup fixture deletes the shared CACHE_DIR from
    # one worker while a test on the other is mid-assertion — an intermittent
    # "cleared == 0" failure that has nothing to do with the code under test.

    def test_rejected_without_admin_key(self):
        response = client.delete("/api/cache")
        assert response.status_code in (401, 403)

    def test_rejected_with_wrong_admin_key(self):
        response = client.delete("/api/cache", headers={"X-Admin-Key": "not-the-key"})
        assert response.status_code in (401, 403)

    def test_wrong_key_does_not_clear_the_cache(self):
        _MEMORY_CACHE["survives-unauthorized-delete"] = {"any": "value"}
        client.delete("/api/cache", headers={"X-Admin-Key": "not-the-key"})
        assert "survives-unauthorized-delete" in _MEMORY_CACHE
