import os

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
