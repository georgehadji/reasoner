"""Tests for automatic rollback / graceful degradation behavior.

These tests verify that every enhancement auto-disables or falls back
when its dependency is missing, without human intervention.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner.core.health_validator import (
    _check_openrouter_key,
    _check_perplexity_key,
    validate_all,
)
from reasoner.core.rerank import rerank_documents
from reasoner.core.settings import settings
from reasoner.pipeline import ReasonerPipeline


class TestAutoKeyValidation:
    @pytest.mark.asyncio
    async def test_invalid_openrouter_key_detected(self):
        assert await _check_openrouter_key("") is False
        assert await _check_openrouter_key("invalid") is False
        assert await _check_openrouter_key("sk-or-v1-valid") is True

    @pytest.mark.asyncio
    async def test_invalid_perplexity_key_detected(self):
        assert await _check_perplexity_key("") is False
        assert await _check_perplexity_key("invalid") is False
        assert await _check_perplexity_key("pplx-valid") is True


class TestAutoDisableCohereRerank:
    @pytest.mark.asyncio
    async def test_auto_disables_cohere_when_no_openrouter_key(self):
        original = settings.COHERE_RERANK_ENABLED
        try:
            settings.COHERE_RERANK_ENABLED = True
            with patch.object(settings, "OPENROUTER_API_KEY", None):
                report = await validate_all()

            cohere_result = next(r for r in report.results if r.feature == "Cohere Rerank")
            assert cohere_result.enabled is False
            assert cohere_result.auto_corrected is True
            assert settings.COHERE_RERANK_ENABLED is False
        finally:
            settings.COHERE_RERANK_ENABLED = original

    @pytest.mark.asyncio
    async def test_keeps_cohere_enabled_when_key_present(self):
        original = settings.COHERE_RERANK_ENABLED
        try:
            settings.COHERE_RERANK_ENABLED = True
            with patch.object(settings, "OPENROUTER_API_KEY", "sk-or-v1-test"):
                report = await validate_all()

            cohere_result = next(r for r in report.results if r.feature == "Cohere Rerank")
            assert cohere_result.enabled is True
            assert settings.COHERE_RERANK_ENABLED is True
        finally:
            settings.COHERE_RERANK_ENABLED = original


class TestAutoDisableSemanticRetrieval:
    @pytest.mark.asyncio
    async def test_auto_disables_semantic_retrieval_when_no_openrouter_key(self):
        original = settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED
        try:
            settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED = True
            with patch.object(settings, "OPENROUTER_API_KEY", None):
                report = await validate_all()

            doc_result = next(r for r in report.results if r.feature == "Document Semantic Retrieval")
            assert doc_result.enabled is False
            assert doc_result.auto_corrected is True
            assert settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED is False
        finally:
            settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED = original


class TestAutoFallbackRerank:
    @pytest.mark.asyncio
    async def test_rerank_falls_back_to_nemotron_when_cohere_api_fails(self):
        """When Cohere's rerank call fails, rerank_documents now cascades to
        the Nemotron reranker instead of just giving up and returning docs
        unchanged — a real resilience improvement (core/rerank.py's except
        branch calls rerank_via_nemotron()). Mock that fallback directly
        rather than simulating Nemotron's own HTTP/logprobs semantics.
        """
        docs = [{"title": "a"}, {"title": "b"}]

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("OpenRouter down")

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch.object(settings, "OPENROUTER_API_KEY", "sk-or-v1-test"):
                # Pin explicitly rather than relying on the True default: an
                # earlier test in this xdist worker may have booted the
                # FastAPI app lifespan with a not-"sk-"-prefixed
                # OPENROUTER_API_KEY (e.g. CI's placeholder key), and
                # health_validator.validate_all() auto-corrects by assigning
                # settings.COHERE_RERANK_ENABLED = False directly on the
                # shared singleton with no restore (see
                # TestAutoDisableCohereRerank above, which guards against
                # exactly this). Without pinning it here, this test's own
                # rerank_documents() call would short-circuit to "return
                # documents" before ever reaching Cohere or the Nemotron
                # fallback under test.
                with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                    with patch(
                        "reasoner.core.rerank.rerank_via_nemotron",
                        new_callable=AsyncMock,
                        return_value=docs,
                    ) as mock_nemotron:
                        result = await rerank_documents("query", docs)

        mock_nemotron.assert_awaited_once()
        assert result == docs

    @pytest.mark.asyncio
    async def test_rerank_returns_docs_unchanged_when_disabled(self):
        docs = [{"title": "a"}, {"title": "b"}]
        with patch.object(settings, "COHERE_RERANK_ENABLED", False):
            result = await rerank_documents("query", docs)
        assert result == docs

    @pytest.mark.asyncio
    async def test_rerank_returns_docs_unchanged_when_no_key(self):
        docs = [{"title": "a"}, {"title": "b"}]
        with patch.object(settings, "OPENROUTER_API_KEY", None):
            with patch.object(settings, "COHERE_RERANK_ENABLED", True):
                result = await rerank_documents("query", docs)
        assert result == docs


class TestAutoFallbackAttachmentContext:
    @pytest.mark.asyncio
    async def test_pipeline_falls_back_to_full_text_on_semantic_error(self):
        pipeline = ReasonerPipeline(
            router=MagicMock(),
            top_k=3,
            verbose=False,
            preset_name="auto-budget",
        )

        mock_store = MagicMock()
        mock_store.retrieve = AsyncMock(side_effect=Exception("embedder failed"))

        with patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True):
            with patch("reasoner.documents.vector_store.DocumentVectorStore", return_value=mock_store):
                attachments = [
                    {"file_id": "abc", "filename": "doc.pdf", "extracted_text": "full text here"}
                ]
                result = await pipeline._build_attachment_context(attachments, query="test")

        assert "full content provided below" in result
        assert "full text here" in result

    @pytest.mark.asyncio
    async def test_pipeline_uses_semantic_when_enabled_and_working(self):
        pipeline = ReasonerPipeline(
            router=MagicMock(),
            top_k=3,
            verbose=False,
            preset_name="auto-budget",
        )

        mock_store = MagicMock()
        mock_store.retrieve = AsyncMock(return_value=["relevant chunk 1", "relevant chunk 2"])

        with patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True):
            with patch("reasoner.documents.vector_store.DocumentVectorStore", return_value=mock_store):
                attachments = [
                    {"file_id": "abc", "filename": "doc.pdf", "extracted_text": "full text here"}
                ]
                result = await pipeline._build_attachment_context(attachments, query="test")

        assert "semantic excerpts" in result
        assert "relevant chunk 1" in result
