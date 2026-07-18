import os

# Mirror the env the CI test job sets (.github/workflows/test.yml) so a local
# `pytest tests/` behaves the same as CI. Without JWT_SECRET_KEY in particular,
# ~9 test modules fail at COLLECTION -- LocalAuthAdapter validates the key's
# length when it is constructed at module import time (e.g. test_ocr.py), so
# the error happens before any test runs and takes the whole file with it.
#
# setdefault, not assignment: a value already exported by CI or by a developer
# with real credentials always wins. These are placeholders, never credentials,
# and they are confined to the test process -- production still requires the
# real values via settings.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("CSRF_ENFORCE_BACKEND", "false")
os.environ.setdefault("OPENROUTER_API_KEY", "test-dummy-openrouter-key-placeholder")
os.environ.setdefault("RATE_LIMITER_REDIS_FAILURE_MODE", "fail_open")

import httpx
import pytest
import asyncio

from reasoner.application.event_bus.bus import reset_event_bus
from reasoner.infrastructure.observability.langfuse_subscriber import reset_langfuse
from reasoner.token_cache import reset_token_cache


@pytest.fixture(scope="session")
def searxng_container() -> str:
    """Return the SearXNG base URL and skip if the instance is unreachable."""
    url = os.environ.get("SEARXNG_URL", "http://localhost:8888").rstrip("/")
    try:
        resp = httpx.get(url, timeout=5)
        if resp.status_code >= 500:
            pytest.skip(f"SearXNG at {url} returned {resp.status_code} — skipping integration tests")
    except httpx.TransportError:
        pytest.skip(f"SearXNG not reachable at {url} — skipping integration tests")
    return url


@pytest.fixture(scope="session")
def searxng_client(searxng_container: str):
    """Return a DiscoveryClient pointed at the live SearXNG instance."""
    from reasoner.infrastructure.search.discovery import DiscoveryClient
    return DiscoveryClient(base_url=searxng_container)


@pytest.fixture(autouse=True)
async def auto_clean_state():
    """Fixture to reset all global state between tests."""
    # Ensure event loop is running for async resets
    if asyncio.get_event_loop().is_running():
        reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        # If loop is not running, create a new one for the reset operations
        async def _run_resets():
            reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets())

    yield

    # Also reset after the test
    if asyncio.get_event_loop().is_running():
        reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        async def _run_resets_after():
            reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets_after())
