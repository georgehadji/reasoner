"""Unit tests for SearXNG circuit breaker integration in DiscoveryClient."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from reasoner.circuit_breaker import CircuitState


@pytest.fixture(autouse=True)
async def inject_memory_circuit():
    """Inject a fresh in-memory CircuitBreaker for test isolation.

    CI may set CIRCUIT_BREAKER_MODE=redis, returning a RedisCircuitBreaker
    that has no .state property and can't be deterministically controlled
    without a live Redis. We always use the plain in-memory CircuitBreaker
    for unit tests.
    """
    import reasoner.core.search as search_module
    from reasoner.infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    test_cb = CircuitBreaker("searxng", CircuitBreakerConfig(
        failure_threshold=5, success_threshold=2, timeout_seconds=30.0,
    ))
    original_cb = search_module._SEARXNG_CB
    search_module._SEARXNG_CB = test_cb

    await test_cb.reset()
    yield test_cb
    await test_cb.reset()
    search_module._SEARXNG_CB = original_cb


class TestSearXNGCircuitBreaker:
    """Verify circuit breaker integration with DiscoveryClient."""

    @pytest.mark.asyncio
    async def test_search_records_success_on_ok_response(self, inject_memory_circuit):
        """When SearXNG returns results, circuit records success."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient

        cb = inject_memory_circuit
        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client.adapter, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (
                [{"title": "Test", "url": "http://t.com", "content": "content"}],
                1,
            )
            result = await client.search("test query")

        assert len(result) == 1
        assert cb.stats.consecutive_successes >= 1
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_search_records_failure_on_exception(self, inject_memory_circuit):
        """When SearXNG throws, circuit records failure."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient

        cb = inject_memory_circuit
        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client.adapter, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = ConnectionError("Connection refused")
            result = await client.search("test query")

        assert result == []
        assert cb.stats.consecutive_failures >= 1

    @pytest.mark.asyncio
    async def test_open_circuit_returns_empty_immediately(self, inject_memory_circuit):
        """When circuit is open, search returns [] without calling SearXNG."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient

        cb = inject_memory_circuit
        for _ in range(5):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client.adapter, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            result = await client.search("test query")

        assert result == []
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_half_open_then_closes_on_success(self, inject_memory_circuit):
        """After timeout, circuit enters half-open and closes on success."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient

        cb = inject_memory_circuit
        original_threshold = cb.config.success_threshold
        cb.config.success_threshold = 1

        for _ in range(5):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        import time
        cb._last_state_change = time.monotonic() - cb.config.timeout_seconds

        assert await cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client.adapter, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (
                [{"title": "Test", "url": "http://t.com", "content": "content"}],
                1,
            )
            result = await client.search("test query")

        assert len(result) == 1
        assert cb.state == CircuitState.CLOSED

        cb.config.success_threshold = original_threshold

    @pytest.mark.asyncio
    async def test_get_search_client_prefers_perplexity_when_circuit_open(self, inject_memory_circuit):
        """When SearXNG circuit is open and Perplexity key exists, use Perplexity."""
        from reasoner.infrastructure.search.discovery import get_search_client

        cb = inject_memory_circuit
        for _ in range(5):
            await cb.record_failure()

        with patch("reasoner.infrastructure.search.discovery.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "fake-key"
            with patch("reasoner.infrastructure.search.discovery.PerplexitySearchClient") as MockP:
                instance = MockP.return_value
                instance.search = AsyncMock(return_value=[])
                client, _ = await get_search_client()

        assert isinstance(client, MockP.return_value.__class__)
