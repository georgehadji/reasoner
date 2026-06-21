"""Unit tests for SearXNG circuit breaker integration in DiscoveryClient."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from reasoner.circuit_breaker import CircuitState


@pytest.fixture(autouse=True)
async def reset_searxng_circuit():
    """Reset the SearXNG circuit breaker before each test."""
    from reasoner.core.search import _get_searxng_cb
    cb = _get_searxng_cb()
    await cb.reset()
    yield
    cb = _get_searxng_cb()
    await cb.reset()


class TestSearXNGCircuitBreaker:
    """Verify circuit breaker integration with DiscoveryClient."""

    @pytest.mark.asyncio
    async def test_search_records_success_on_ok_response(self):
        """When SearXNG returns results, circuit records success."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient
        from reasoner.core.search import _SEARXNG_CB

        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (
                [{"title": "Test", "url": "http://t.com", "content": "content"}],
                1,
            )
            result = await client.search("test query")

        assert len(result) == 1
        assert _SEARXNG_CB.stats.consecutive_successes >= 1
        assert _SEARXNG_CB.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_search_records_failure_on_exception(self):
        """When SearXNG throws, circuit records failure."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient
        from reasoner.core.search import _SEARXNG_CB

        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = ConnectionError("Connection refused")
            result = await client.search("test query")

        assert result == []
        assert _SEARXNG_CB.stats.consecutive_failures >= 1

    @pytest.mark.asyncio
    async def test_open_circuit_returns_empty_immediately(self):
        """When circuit is open, search returns [] without calling SearXNG."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient
        from reasoner.core.search import _SEARXNG_CB

        # Force circuit open (default failure_threshold = 5)
        for _ in range(5):
            await _SEARXNG_CB.record_failure()
        assert _SEARXNG_CB.state == CircuitState.OPEN

        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            result = await client.search("test query")

        assert result == []
        mock_fetch.assert_not_called()  # No upstream call!

    @pytest.mark.asyncio
    async def test_circuit_half_open_then_closes_on_success(self):
        """After timeout, circuit enters half-open and closes on success."""
        from reasoner.infrastructure.search.discovery import DiscoveryClient
        from reasoner.core.search import _SEARXNG_CB

        # Lower threshold so one success closes the circuit
        original_threshold = _SEARXNG_CB.config.success_threshold
        _SEARXNG_CB.config.success_threshold = 1

        # Force open
        for _ in range(5):
            await _SEARXNG_CB.record_failure()
        assert _SEARXNG_CB.state == CircuitState.OPEN

        # Simulate timeout elapsed by resetting last_state_change
        import time
        _SEARXNG_CB._last_state_change = time.monotonic() - _SEARXNG_CB.config.timeout_seconds

        # Next can_execute() should transition to HALF_OPEN
        assert await _SEARXNG_CB.can_execute()
        assert _SEARXNG_CB.state == CircuitState.HALF_OPEN

        # A successful search should close the circuit
        client = DiscoveryClient(base_url="http://localhost:8888")
        with patch.object(client, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (
                [{"title": "Test", "url": "http://t.com", "content": "content"}],
                1,
            )
            result = await client.search("test query")

        assert len(result) == 1
        assert _SEARXNG_CB.state == CircuitState.CLOSED

        _SEARXNG_CB.config.success_threshold = original_threshold

    @pytest.mark.asyncio
    async def test_get_search_client_prefers_perplexity_when_circuit_open(self):
        """When SearXNG circuit is open and Perplexity key exists, use Perplexity."""
        from reasoner.core.search import _SEARXNG_CB, get_search_client

        # Force circuit open
        for _ in range(5):
            await _SEARXNG_CB.record_failure()

        with patch("reasoner.core.search.settings.OPENROUTER_API_KEY", "fake-key"):
            with patch("reasoner.core.search.PerplexitySearchClient") as MockP:
                instance = MockP.return_value
                instance.search = AsyncMock(return_value=[])
                client, _ = await get_search_client()

        assert isinstance(client, MockP.return_value.__class__)
