"""Integration test fixtures: server URL, CSRF token, SSE helpers."""

import os

import httpx
import pytest

# Default base URL — override with REASONER_TEST_URL env var
BASE_URL = os.environ.get("REASONER_TEST_URL", "http://localhost:8003")

# Per-test timeout in seconds
TEST_TIMEOUT = int(os.environ.get("REASONER_TEST_TIMEOUT", "120"))


@pytest.fixture(autouse=True)
def _reset_shared_rate_limiter():
    """Give every in-process (TestClient-based) integration test a full
    token bucket to start from.

    check_rate_limit's RateLimiter (reasoner/api/dependencies.py) is a
    process-wide singleton keyed by client_id -- for an unauthenticated
    starlette TestClient that's IP+User-Agent, which is the same for every
    test in the process. In CI (no Redis, RATE_LIMITER_REDIS_FAILURE_MODE=
    fail_open) it degrades to the in-memory bucket, so burst capacity
    (default 10) accumulates depletion across every rate-limited endpoint
    any earlier test in the same pytest-xdist worker happened to hit --
    including tests outside this directory entirely. Resetting before each
    integration test isolates it from that ambient cross-test traffic
    without changing production behavior (a real deployment never resets
    mid-process).

    reset_local_buckets(), not reset_all(). settings.RATE_LIMITER_MODE
    defaults to "redis", so whenever a Redis/Valkey is actually reachable --
    a developer running `pytest tests/integration` against a deployment with
    the project .env loaded, which is what the base_url/REASONER_TEST_URL
    fixtures below exist for -- reset_all() takes the branch its own source
    labels "Danger zone", scan_iter("rate_limit:*") + delete. That wipes the
    throttling state of every live client of that environment, once per test,
    and races the buckets of sibling `-n auto` xdist workers. The only state
    this suite owns is its own process's in-memory table, so that is the only
    state it clears.

    Synchronous on purpose. reset_all() is a coroutine that awaits the
    limiter's process-wide asyncio.Lock; pytest-asyncio runs fixtures on the
    session-scoped loop (pytest.ini: asyncio_default_fixture_loop_scope =
    session) while the app under Starlette's TestClient takes that same lock
    from the portal's own loop. asyncio.Lock binds itself to a loop on its
    first contended acquire and raises RuntimeError for every acquire from a
    different loop after that -- latent only because nothing contends it
    today. A sync fixture cannot touch the lock at all.
    """
    from reasoner.api.dependencies import _get_rate_limiter_instance

    _get_rate_limiter_instance().reset_local_buckets()
    yield


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
