"""Tests for SearchClient factory routing and SearchService integration."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from reasoner.application.services.search_service import SearchService


class TestSearchServiceRouting:
    """Verify SearchService.search() routes through get_search_client factory."""

    @pytest.mark.asyncio
    async def test_search_service_uses_factory(self):
        """SearchService.search must call get_search_client, not get_discovery_client directly."""
        mock_client = AsyncMock()
        mock_client.search.return_value = [
            {"title": "Test", "url": "http://example.com", "snippet": "result"}
        ]

        with patch("reasoner.core.search.get_search_client", new_callable=AsyncMock) as mock_factory:
            mock_factory.return_value = (mock_client, None)
            service = SearchService()
            results = await service.search("test query", source_type="general", num_results=5)

        mock_factory.assert_awaited_once()
        mock_client.search.assert_awaited_once_with("test query", num_results=5, source_type="general")
        assert len(results) == 1
        assert results[0]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_search_service_fallback_on_failure(self):
        """SearchService must return empty list when factory raises."""
        with patch("reasoner.core.search.get_search_client") as mock_factory:
            mock_factory.side_effect = RuntimeError("search unavailable")
            service = SearchService()
            results = await service.search("test query")

        assert results == []


class TestGetSearchClientFactory:
    """Verify get_search_client factory selects the correct implementation."""

    @pytest.mark.asyncio
    async def test_perplexity_selected_when_openrouter_key_present(self):
        """When OPENROUTER_API_KEY is set, return PerplexitySearchClient."""
        from reasoner.core.search import get_search_client, PerplexitySearchClient

        with patch("reasoner.infrastructure.search.discovery.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test-key"
            mock_settings.PERPLEXITY_API_KEY = ""
            with patch("reasoner.infrastructure.search.discovery.PerplexitySearchClient") as mock_pplx:
                mock_instance = MagicMock()
                mock_pplx.return_value = mock_instance
                client, source_type = await get_search_client()
                mock_pplx.assert_called_once()
                assert client is mock_instance

    @pytest.mark.asyncio
    async def test_fallback_client_when_all_keys_missing(self):
        """With no backend keys, the factory falls back to PerplexitySearchClient (strategy 4)."""
        from reasoner.core.search import get_search_client

        with patch("reasoner.infrastructure.search.discovery.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.PERPLEXITY_API_KEY = ""
            mock_settings.TAVILY_API_KEY = ""
            mock_settings.TAVILY_SEARCH_ENABLED = False
            mock_settings.BRAVE_SEARCH_API_KEY = ""
            mock_settings.BRAVE_SEARCH_ENABLED = False
            with patch("reasoner.infrastructure.search.discovery.PerplexitySearchClient") as mock_pplx:
                mock_instance = MagicMock()
                mock_pplx.return_value = mock_instance
                client, source_type = await get_search_client()

        mock_pplx.assert_called_once()
        assert client is mock_instance
