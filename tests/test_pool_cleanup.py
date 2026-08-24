"""Tests for HTTP pool cleanup fix (BUG-002 regression)."""

import asyncio

import pytest

from reasoner.llm import OpenAICompatibleProvider


@pytest.fixture(autouse=True)
def cleanup_after_each_test():
    """Clean up pool state after each test."""
    yield
    # Reset state for next test (synchronous cleanup)
    OpenAICompatibleProvider._shared_pool = None
    OpenAICompatibleProvider._pool_closed = False
    OpenAICompatibleProvider._pool_lock = None
    OpenAICompatibleProvider._pool_init_lock = None


class TestSharedPoolCleanup:
    """BUG-002 regression tests: Shared HTTP pool must be properly cleaned up."""

    @pytest.mark.asyncio
    async def test_close_shared_pool_basic(self):
        """Test basic pool close functionality."""
        # Create a provider (this initializes the pool)
        provider = OpenAICompatibleProvider(
            model="deepseek-v3",
            api_key="test-key",
            base_url="https://test.api"
        )

        # Verify pool was created
        assert OpenAICompatibleProvider._shared_pool is not None
        assert OpenAICompatibleProvider._pool_closed == False

        # Close the pool
        await OpenAICompatibleProvider.close_shared_pool()

        # Verify pool was closed
        assert OpenAICompatibleProvider._shared_pool is None
        assert OpenAICompatibleProvider._pool_closed == True

    @pytest.mark.asyncio
    async def test_close_shared_pool_idempotent(self):
        """Test that calling close multiple times is safe."""
        # Create a provider
        provider = OpenAICompatibleProvider(
            model="qwen3-max",
            api_key="test-key",
            base_url="https://test.api"
        )

        # Close multiple times - should not raise
        await OpenAICompatibleProvider.close_shared_pool()
        await OpenAICompatibleProvider.close_shared_pool()
        await OpenAICompatibleProvider.close_shared_pool()

        # Should still be closed
        assert OpenAICompatibleProvider._shared_pool is None
        assert OpenAICompatibleProvider._pool_closed == True

    @pytest.mark.asyncio
    async def test_close_before_initialization(self):
        """Test closing pool before it's created."""
        # Ensure pool is not initialized
        OpenAICompatibleProvider._shared_pool = None
        OpenAICompatibleProvider._pool_closed = False

        # Close without initialization - should not raise
        await OpenAICompatibleProvider.close_shared_pool()

        assert OpenAICompatibleProvider._pool_closed == True

    @pytest.mark.asyncio
    async def test_concurrent_close_calls(self):
        """Test that concurrent close calls are handled safely."""
        # Create a provider
        provider = OpenAICompatibleProvider(
            model="kimi-k2",
            api_key="test-key",
            base_url="https://test.api"
        )

        # Launch multiple concurrent close calls
        async def close_it():
            await OpenAICompatibleProvider.close_shared_pool()

        tasks = [close_it() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should be closed
        assert OpenAICompatibleProvider._shared_pool is None
        assert OpenAICompatibleProvider._pool_closed == True

    @pytest.mark.asyncio
    async def test_pool_recreated_after_close(self):
        """Test that pool can be recreated after closing."""
        # Create and close
        provider1 = OpenAICompatibleProvider(
            model="glm-4-plus",
            api_key="test-key",
            base_url="https://test.api"
        )
        await OpenAICompatibleProvider.close_shared_pool()

        # Verify closed
        assert OpenAICompatibleProvider._shared_pool is None
        assert OpenAICompatibleProvider._pool_closed == True

        # Create new provider - should recreate pool
        provider2 = OpenAICompatibleProvider(
            model="mistral-large-latest",
            api_key="test-key",
            base_url="https://test.api"
        )

        # Pool should be recreated
        assert OpenAICompatibleProvider._shared_pool is not None
        assert OpenAICompatibleProvider._pool_closed == False


class TestPoolLockInitialization:
    """Test pool lock initialization."""

    @pytest.mark.asyncio
    async def test_lock_created_on_first_close(self):
        """Test that lock is created when first close is called."""
        # Ensure clean state
        OpenAICompatibleProvider._pool_lock = None
        OpenAICompatibleProvider._shared_pool = None
        OpenAICompatibleProvider._pool_closed = False

        # Call close (which creates lock)
        await OpenAICompatibleProvider.close_shared_pool()

        # Lock should exist (created during close)
        assert OpenAICompatibleProvider._pool_lock is not None


class TestSharedPoolRaceFreeInit:
    """BUG-002 regression: shared pool must only be created once even under concurrent init."""

    def test_concurrent_init_creates_single_pool(self):
        """Multiple simultaneous provider instantiations must create only one httpx client."""
        import time
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch

        import httpx

        OpenAICompatibleProvider._shared_pool = None
        OpenAICompatibleProvider._pool_closed = False
        OpenAICompatibleProvider._pool_init_lock = None

        call_count = 0
        original_async_client = httpx.AsyncClient

        def counting_async_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            time.sleep(0.05)  # Force overlap to exercise the lock
            return original_async_client(*args, **kwargs)

        with patch("httpx.AsyncClient", side_effect=counting_async_client):
            with patch("reasoner.infrastructure.llm.providers.openai_compat.openai.AsyncOpenAI", lambda **kwargs: None):
                def create_provider():
                    return OpenAICompatibleProvider(
                        model="deepseek-v3",
                        api_key="test-key",
                        base_url="https://test.api",
                    )

                with ThreadPoolExecutor(max_workers=5) as ex:
                    futures = [ex.submit(create_provider) for _ in range(5)]
                    providers = [f.result() for f in futures]

        assert call_count == 1, f"Expected exactly one AsyncClient creation, got {call_count}"
        assert OpenAICompatibleProvider._shared_pool is not None
        for p in providers:
            assert p is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
