"""Tests for Neuro Embedding Provider Fallbacks."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from reasoner.neuro.providers import (
    ResilientEmbedding,
    OpenAIEmbedding,
    OllamaEmbedding,
    _create_embedding,
)
from reasoner.neuro.config import ProviderConfig, ResilientProviderConfig

class TestResilientEmbedding:
    @pytest.mark.asyncio
    async def test_embed_fallback_on_primary_failure(self):
        config = ResilientProviderConfig(
            primary=ProviderConfig(provider="openai", model="text-embedding-ada-002", api_key="bad"),
            fallbacks=[ProviderConfig(provider="ollama", model="nomic-embed-text", api_base="http://localhost:11434")],
            circuit_breaker_threshold=1
        )
        resilient = ResilientEmbedding(config)
        
        # Mock primary to fail
        mock_primary_embed = AsyncMock(side_effect=Exception("Primary failed"))
        resilient.primary.embed = mock_primary_embed
        
        # Mock fallback to succeed
        mock_fallback_embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        resilient.fallbacks[0].embed = mock_fallback_embed

        result = await resilient.embed("test text")
        
        assert result == [0.1, 0.2, 0.3]
        mock_primary_embed.assert_called_once_with("test text")
        mock_fallback_embed.assert_called_once_with("test text")
        assert resilient.failed_over is True
        assert resilient.active_label == "ollama/nomic-embed-text"
        
    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_primary_after_threshold(self):
        config = ResilientProviderConfig(
            primary=ProviderConfig(provider="openai", model="text-embedding-ada-002", api_key="bad"),
            fallbacks=[ProviderConfig(provider="ollama", model="nomic-embed-text", api_base="http://localhost:11434")],
            circuit_breaker_threshold=1
        )
        resilient = ResilientEmbedding(config)
        
        # Mock primary to fail
        resilient.primary.embed = AsyncMock(side_effect=Exception("Primary failed"))
        # Mock fallback to succeed
        resilient.fallbacks[0].embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

        # First call fails primary, trips breaker
        await resilient.embed("call 1")
        assert resilient.breaker.is_open is True
        
        # Second call should skip primary entirely
        resilient.primary.embed.reset_mock()
        await resilient.embed("call 2")
        
        resilient.primary.embed.assert_not_called()
        assert resilient.fallbacks[0].embed.call_count == 2

class TestOpenAIEmbedding:
    @pytest.mark.asyncio
    async def test_embed_makes_correct_request(self):
        config = ProviderConfig(
            provider="openai",
            model="text-embedding-3-small",
            api_key="test-key",
            api_base="https://api.openai.com/v1",
        )
        provider = OpenAIEmbedding(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.4, 0.5, 0.6]}]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.embed("hello")

        assert result == [0.4, 0.5, 0.6]
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["model"] == "text-embedding-3-small"
        assert call_args[1]["json"]["input"] == "hello"
        assert "Authorization" in call_args[1]["headers"]
