"""Tests for Perplexity Embed V1 provider integration."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from reasoner.neuro.providers import (
    PerplexityEmbedding,
    EMBEDDING_MAP,
    _create_embedding,
)
from reasoner.neuro.config import ProviderConfig


class TestPerplexityEmbedding:
    @pytest.mark.asyncio
    async def test_embed_makes_correct_request(self):
        config = ProviderConfig(
            provider="perplexity",
            model="perplexity/pplx-embed-v1-0.6b",
            api_key="test-key",
            api_base="https://api.perplexity.ai",
        )
        provider = PerplexityEmbedding(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.embed("hello world")

        assert result == [0.1, 0.2, 0.3]
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["model"] == "perplexity/pplx-embed-v1-0.6b"
        assert call_args[1]["json"]["input"] == "hello world"
        assert "Authorization" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_embed_uses_default_base_url(self):
        config = ProviderConfig(
            provider="perplexity",
            model="perplexity/pplx-embed-v1-0.6b",
            api_key="test-key",
            api_base="",
        )
        provider = PerplexityEmbedding(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.embed("test")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://api.perplexity.ai/embeddings"

    @pytest.mark.asyncio
    async def test_embed_raises_on_api_error(self):
        config = ProviderConfig(
            provider="perplexity",
            model="perplexity/pplx-embed-v1-0.6b",
            api_key="test-key",
        )
        provider = PerplexityEmbedding(config)

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, "_get_client", return_value=mock_client):
            with pytest.raises(Exception, match="API Error"):
                await provider.embed("test")

    @pytest.mark.asyncio
    async def test_health_check_with_key(self):
        config = ProviderConfig(provider="perplexity", api_key="test-key")
        provider = PerplexityEmbedding(config)
        assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_without_key(self):
        config = ProviderConfig(provider="perplexity", api_key="")
        provider = PerplexityEmbedding(config)
        assert await provider.health_check() is False

    def test_label(self):
        config = ProviderConfig(provider="perplexity", model="pplx-embed-v1")
        provider = PerplexityEmbedding(config)
        assert provider.label == "perplexity/pplx-embed-v1"


class TestEmbeddingMap:
    def test_perplexity_in_embedding_map(self):
        assert "perplexity" in EMBEDDING_MAP
        assert EMBEDDING_MAP["perplexity"] is PerplexityEmbedding


class TestCreateEmbedding:
    def test_creates_perplexity_embedding(self):
        config = ProviderConfig(
            provider="perplexity",
            model="perplexity/pplx-embed-v1-0.6b",
            api_key="test-key",
        )
        provider = _create_embedding(config)
        assert isinstance(provider, PerplexityEmbedding)

    def test_unknown_provider_raises(self):
        config = ProviderConfig(provider="nonexistent", model="x")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            _create_embedding(config)
