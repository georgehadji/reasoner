"""Tests for PerplexitySearchClient via OpenRouter."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from reasoner.core.search import PerplexitySearchClient, get_search_client


class TestPerplexitySearchClient:
    """Verify Perplexity search client behavior via OpenRouter."""

    @pytest.mark.asyncio
    async def test_init_without_openrouter_key_raises(self):
        """Without OPENROUTER_API_KEY, build_provider raises ValueError."""
        with patch("reasoner.infrastructure.search.discovery._get_build_provider") as mock_get_bp:
            mock_build = Mock(side_effect=ValueError("API key missing"))
            mock_get_bp.return_value = mock_build
            with pytest.raises(ValueError):
                PerplexitySearchClient()

    @pytest.mark.asyncio
    async def test_successful_search(self):
        """Search returns synthesized result with citations from OpenRouter response."""
        mock_provider = MagicMock()
        mock_provider.model = "perplexity/sonar"
        mock_provider.extra_body = {"web_search_options": {"search_context_size": "low"}}

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test result"
        mock_response.citations = ["https://example.com"]

        mock_provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("reasoner.infrastructure.search.discovery._get_build_provider") as mock_get_bp:
            mock_get_bp.return_value = Mock(return_value=mock_provider)
            client = PerplexitySearchClient()
            results = await client.search("test query")

        assert len(results) == 1
        assert results[0]["source"] == "perplexity"
        assert results[0]["content"] == "Test result"
        assert results[0]["citations"] == ["https://example.com"]

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self):
        """On OpenRouter API error, search returns empty list gracefully."""
        mock_provider = MagicMock()
        mock_provider.model = "perplexity/sonar"
        mock_provider.extra_body = None
        mock_provider.client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        with patch("reasoner.infrastructure.search.discovery._get_build_provider") as mock_get_bp:
            mock_get_bp.return_value = Mock(return_value=mock_provider)
            client = PerplexitySearchClient()
            results = await client.search("test query")

        assert results == []


class TestSearchClientFactory:
    """Verify factory selects correct client based on config."""

    @pytest.mark.asyncio
    async def test_factory_returns_perplexity_when_openrouter_key_set(self):
        with patch("reasoner.infrastructure.search.discovery.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.PERPLEXITY_API_KEY = ""
            with patch("reasoner.infrastructure.search.discovery.PerplexitySearchClient") as mock_pplx:
                mock_instance = Mock()
                mock_pplx.return_value = mock_instance
                client, _ = await get_search_client()
                mock_pplx.assert_called_once()
                assert client is mock_instance

    @pytest.mark.asyncio
    async def test_factory_falls_back_when_openrouter_key_missing(self):
        """With no backend keys, factory falls back to PerplexitySearchClient (strategy 4)."""
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
                client, _ = await get_search_client()
                mock_pplx.assert_called_once()
                assert client is mock_instance
