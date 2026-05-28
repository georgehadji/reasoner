import pytest
import asyncio

from reasoner.application.event_bus.bus import reset_event_bus
from reasoner.infrastructure.observability.langfuse_subscriber import reset_langfuse
from reasoner.token_cache import reset_token_cache


@pytest.fixture(autouse=True)
async def auto_clean_state():
    """Fixture to reset all global state between tests."""
    # Ensure event loop is running for async resets
    if asyncio.get_event_loop().is_running():
        await reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        # If loop is not running, create a new one for the reset operations
        # This should ideally not happen with pytest-asyncio, but as a fallback
        async def _run_resets():
            await reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets())

    yield

    # Also reset after the test
    if asyncio.get_event_loop().is_running():
        await reset_event_bus()
        reset_langfuse()
        await reset_token_cache()
    else:
        async def _run_resets_after():
            await reset_event_bus()
            reset_langfuse()
            await reset_token_cache()
        asyncio.run(_run_resets_after())
