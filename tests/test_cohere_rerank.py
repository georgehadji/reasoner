"""Tests for Cohere Rerank 4 Fast integration via OpenRouter."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from reasoner.core.rerank import (
    rerank_documents,
    rerank_memory_chunks,
    _sanitize_text,
    _is_circuit_open,
)
from reasoner.core.settings import settings
from reasoner.neuro.cache import ContextChunk


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset global circuit breaker state between tests."""
    import reasoner.core.rerank as rerank_module
    rerank_module._failure_count = 0
    rerank_module._last_failure_time = 0.0
    yield


class TestSanitizeText:
    def test_removes_null_bytes(self):
        assert _sanitize_text("he\x00llo") == "hello"

    def test_truncates_to_max_length(self):
        long_text = "a" * 20_000
        result = _sanitize_text(long_text, max_length=1000)
        assert len(result) == 1000

    def test_normalizes_unicode(self):
        # NFKC normalization of full-width characters
        result = _sanitize_text("ＡＢＣ", max_length=100)
        assert result == "ABC"


class TestRerankDocuments:
    @pytest.mark.asyncio
    async def test_returns_unchanged_when_disabled(self):
        with patch.object(settings, "COHERE_RERANK_ENABLED", False):
            docs = [{"title": "a", "content": "b"}]
            result = await rerank_documents("query", docs)
            assert result == docs

    @pytest.mark.asyncio
    async def test_returns_unchanged_for_single_document(self):
        docs = [{"title": "a", "content": "b"}]
        with patch.object(settings, "COHERE_RERANK_ENABLED", True):
            result = await rerank_documents("query", docs)
        assert result == docs

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_api_key(self):
        with patch.object(settings, "OPENROUTER_API_KEY", None):
            with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                docs = [{"title": "a"}, {"title": "b"}]
                result = await rerank_documents("query", docs)
                assert result == docs

    @pytest.mark.asyncio
    async def test_successful_rerank_reorders_documents(self):
        docs = [
            {"title": "Doc 1", "content": "content one"},
            {"title": "Doc 2", "content": "content two"},
            {"title": "Doc 3", "content": "content three"},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"index": 2, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.87},
            ]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                    result = await rerank_documents("query", docs, top_n=2)

        assert len(result) == 2
        assert result[0]["title"] == "Doc 3"
        assert result[0].get("rerank_score") == 0.95
        assert result[1]["title"] == "Doc 1"

    @pytest.mark.asyncio
    async def test_api_failure_falls_back_to_nemotron(self):
        """When Cohere fails, rerank_documents falls back to Nemotron."""
        docs = [{"title": "a"}, {"title": "b"}]

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        nemotron_result = [{"title": "b", "rerank_score": 0.9}, {"title": "a", "rerank_score": 0.1}]
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("reasoner.core.rerank.rerank_via_nemotron", AsyncMock(return_value=nemotron_result)):
                with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                    with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                        # The secondary reranker only runs when explicitly enabled;
                        # otherwise a Cohere failure degrades to unranked documents.
                        with patch.object(settings, "NEMOTRON_RERANK_ENABLED", True):
                            result = await rerank_documents("query", docs)

        assert result == nemotron_result

    @pytest.mark.asyncio
    async def test_empty_results_falls_back_to_nemotron(self):
        """When Cohere returns empty results, rerank_documents falls back to Nemotron."""
        docs = [{"title": "a"}, {"title": "b"}]

        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("reasoner.core.rerank.rerank_via_nemotron", AsyncMock(return_value=docs)):
                with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                    with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                        result = await rerank_documents("query", docs)

        assert result == docs

    @pytest.mark.asyncio
    async def test_limits_documents_to_max(self):
        docs = [{"title": f"doc {i}"} for i in range(150)]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"index": i, "relevance_score": 0.9} for i in range(100)]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                    result = await rerank_documents("query", docs)

        # Verify only 100 docs were sent
        call_args = mock_client.post.call_args
        assert len(call_args[1]["json"]["documents"]) == 100

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        docs = [{"title": "a"}, {"title": "b"}]

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("reasoner.core.rerank.rerank_via_nemotron", AsyncMock(return_value=docs)):
                with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                    with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                        # 3 failures should open circuit
                        for _ in range(4):
                            result = await rerank_documents("query", docs)
                            assert result == docs

        # After 3 failures, circuit should be open
        assert await _is_circuit_open() is True


class TestRerankMemoryChunks:
    @pytest.mark.asyncio
    async def test_reranks_context_chunks(self):
        chunks = [
            ContextChunk("content A", "source1", 0.5, "L1"),
            ContextChunk("content B", "source2", 0.6, "L1"),
            ContextChunk("content C", "source3", 0.7, "L1"),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 2, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.80},
            ]
        }
        mock_response.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
                with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                    result = await rerank_memory_chunks("query", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].content == "content C"
        assert result[1].content == "content A"

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_disabled(self):
        with patch.object(settings, "COHERE_RERANK_ENABLED", False):
            chunks = [ContextChunk("a", "s", 0.5, "L1")]
            result = await rerank_memory_chunks("query", chunks)
            assert result == chunks


@pytest.mark.asyncio
async def test_nemotron_rerank_without_model_returns_documents_unchanged():
    """An unset NEMOTRON_RERANK_MODEL must not attempt a call.

    The default used to be a removed endpoint, so enabling this path spent one
    request per document on a dead URL and then stamped every document with the
    neutral 0.5 error score.
    """
    from reasoner.core.rerank import rerank_via_nemotron

    docs = [{"title": "a"}, {"title": "b"}]
    with patch.object(settings, "OPENROUTER_API_KEY", "test-key"):
        with patch.object(settings, "NEMOTRON_RERANK_MODEL", ""):
            with patch("httpx.AsyncClient") as mock_cls:
                result = await rerank_via_nemotron("query", docs)

    assert result == docs
    mock_cls.assert_not_called()
