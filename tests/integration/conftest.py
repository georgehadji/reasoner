"""Integration test fixtures: server URL, CSRF token, SSE helpers."""

import os

import httpx
import pytest


# Default base URL — override with REASONER_TEST_URL env var
BASE_URL = os.environ.get("REASONER_TEST_URL", "http://localhost:8003")

# Per-test timeout in seconds
TEST_TIMEOUT = int(os.environ.get("REASONER_TEST_TIMEOUT", "120"))


@pytest.fixture(scope="session")
def base_url() -> str:
    """Return the backend base URL for integration tests."""
    return BASE_URL


@pytest.fixture(scope="session")
def test_timeout() -> int:
    """Per-preset test timeout."""
    return TEST_TIMEOUT


@pytest.fixture(scope="session")
async def csrf_token(base_url: str) -> str:
    """Fetch a fresh CSRF token from the running backend (session-scoped)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        r = await client.post(f"{base_url}/api/csrf")
        assert r.status_code == 200, f"CSRF endpoint returned {r.status_code}: {r.text}"
        return r.json()["token"]


@pytest.fixture
async def api_client(base_url: str, test_timeout: int):
    """Return an httpx.AsyncClient pre-configured for the backend."""
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(test_timeout),
    ) as client:
        yield client
