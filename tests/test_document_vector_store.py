"""Tests for Document Semantic Retrieval (Phase 4)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner.core.settings import settings
from reasoner.documents.vector_store import (
    DocumentVectorStore,
    _chunk_text,
    _cosine_similarity,
)
from reasoner.uploader import UPLOAD_DIR


class TestChunkText:
    def test_empty_text(self):
        assert _chunk_text("", 100, 20) == []

    def test_single_chunk(self):
        text = "hello world"
        assert _chunk_text(text, 100, 20) == ["hello world"]

    def test_multiple_chunks_with_overlap(self):
        text = "a" * 100
        chunks = _chunk_text(text, 30, 10)
        # step = 20; indices: 0, 20, 40, 60, 80 → 5 chunks
        assert len(chunks) == 5
        assert chunks[0] == "a" * 30
        assert chunks[1] == "a" * 30  # overlap 10, so 20-50

    def test_max_chunks_truncation(self):
        text = "word " * 2000
        chunks = _chunk_text(text, 10, 2)
        assert len(chunks) == 500  # capped at _MAX_CHUNKS_PER_FILE


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestDocumentVectorStore:
    def setup_method(self):
        self.store = DocumentVectorStore()
        # Clean up any leftover sidecars
        for f in UPLOAD_DIR.glob("*.vectors.json"):
            if f.name.startswith("test-"):
                f.unlink(missing_ok=True)
        for f in UPLOAD_DIR.glob("test-*.meta.json"):
            f.unlink(missing_ok=True)

    def teardown_method(self):
        for f in UPLOAD_DIR.glob("*.vectors.json"):
            if f.name.startswith("test-"):
                f.unlink(missing_ok=True)
        for f in UPLOAD_DIR.glob("test-*.meta.json"):
            f.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_index_file_creates_sidecar(self):
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        store = DocumentVectorStore(embedder=mock_embedder)

        file_id = "test-index-001"
        text = "This is a sample document. It has multiple sentences. " * 10
        count = await store.index_file(file_id, text, chunk_size=50, chunk_overlap=10)

        assert count > 0
        sidecar_path = UPLOAD_DIR / f"{file_id}.vectors.json"
        assert sidecar_path.exists()

        # Sidecars are encrypted at rest (security-remediation-plan.md
        # Phase 4 item 5) -- the on-disk envelope is {"encrypted": true,
        # "payload": <ciphertext>}, not the sidecar shape directly.
        from reasoner.security.encryption import get_encryption_service

        envelope = json.loads(sidecar_path.read_text())
        assert envelope["encrypted"] is True
        data = json.loads(get_encryption_service().decrypt(envelope["payload"]))
        assert data["file_id"] == file_id
        assert data["chunk_count"] == count
        assert len(data["chunks"]) == count
        assert all("text" in c and "embedding" in c for c in data["chunks"])

    @pytest.mark.asyncio
    async def test_index_file_returns_zero_without_embedder(self):
        store = DocumentVectorStore()
        with patch.object(store, "_get_embedder", return_value=None):
            count = await store.index_file("test-none", "some text")
        assert count == 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_relevant_chunks(self):
        mock_embedder = MagicMock()
        # Return different embeddings so similarity sorts them
        mock_embedder.embed = AsyncMock(side_effect=[
            [1.0, 0.0, 0.0],  # query embedding
        ])
        store = DocumentVectorStore(embedder=mock_embedder)

        file_id = "test-retrieve-001"
        (UPLOAD_DIR / f"{file_id}.meta.json").write_text(
            json.dumps({"user_id": "user-1"})
        )
        # Pre-create sidecar manually
        sidecar = {
            "file_id": file_id,
            "chunk_count": 3,
            "chunks": [
                {"text": "irrelevant content about apples", "embedding": [0.0, 1.0, 0.0]},
                {"text": "relevant content about query topic", "embedding": [0.9, 0.1, 0.0]},
                {"text": "somewhat related content", "embedding": [0.5, 0.5, 0.0]},
            ],
        }
        (UPLOAD_DIR / f"{file_id}.vectors.json").write_text(json.dumps(sidecar))

        results = await store.retrieve("test query", [file_id], top_k=2, user_id="user-1")
        assert len(results) == 2
        assert "relevant content" in results[0]
        assert "somewhat related" in results[1]

    @pytest.mark.asyncio
    async def test_retrieve_refuses_unscoped_or_foreign_files(self):
        file_id = "test-private-001"
        (UPLOAD_DIR / f"{file_id}.meta.json").write_text(
            json.dumps({"user_id": "owner-1"})
        )
        (UPLOAD_DIR / f"{file_id}.vectors.json").write_text(
            json.dumps({"file_id": file_id, "chunks": [{"text": "secret", "embedding": [1.0]}]})
        )
        embedder = MagicMock()
        embedder.embed = AsyncMock(return_value=[1.0])
        store = DocumentVectorStore(embedder=embedder)

        assert await store.retrieve("q", [file_id]) == []
        assert await store.retrieve("q", [file_id], user_id="other-user") == []

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_for_missing_sidecar(self):
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[1.0, 0.0])
        store = DocumentVectorStore(embedder=mock_embedder)

        results = await store.retrieve("query", ["nonexistent-id"], top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_without_embedder(self):
        store = DocumentVectorStore(embedder=None)
        results = await store.retrieve("query", ["any-id"], top_k=5)
        assert results == []

    def test_delete_index_removes_sidecar(self):
        file_id = "test-delete-001"
        sidecar_path = UPLOAD_DIR / f"{file_id}.vectors.json"
        sidecar_path.write_text('{"file_id": "test-delete-001"}')

        assert sidecar_path.exists()
        result = self.store.delete_index(file_id)
        assert result is True
        assert not sidecar_path.exists()

    def test_delete_index_returns_false_for_missing(self):
        result = self.store.delete_index("totally-missing")
        assert result is False


class TestSemanticAttachmentContext:
    @pytest.mark.asyncio
    async def test_semantic_path_uses_excerpts_when_enabled(self):
        from reasoner.pipeline import ReasonerPipeline

        # Create pipeline instance
        pipeline = ReasonerPipeline(
            router=MagicMock(),
            top_k=3,
            verbose=False,
            preset_name="auto-budget",
        )

        # Mock the vector store
        mock_store = MagicMock()
        mock_store.retrieve = AsyncMock(return_value=[
            "First relevant passage about machine learning.",
            "Second relevant passage about neural networks.",
        ])

        with patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True):
            with patch("reasoner.documents.vector_store.DocumentVectorStore", return_value=mock_store):
                attachments = [
                    {"file_id": "abc123", "filename": "paper.pdf", "extracted_text": "lots of text..."}
                ]
                result = await pipeline._build_attachment_context(attachments, query="machine learning")

        assert "semantic excerpts" in result
        assert "First relevant passage" in result
        assert "Second relevant passage" in result
        mock_store.retrieve.assert_awaited_once_with("machine learning", ["abc123"], top_k=5, user_id=None)

    @pytest.mark.asyncio
    async def test_fallback_to_full_text_when_disabled(self):
        from reasoner.pipeline import ReasonerPipeline

        pipeline = ReasonerPipeline(
            router=MagicMock(),
            top_k=3,
            verbose=False,
            preset_name="auto-budget",
        )

        with patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", False):
            attachments = [
                {"file_id": "abc123", "filename": "paper.pdf", "extracted_text": "full document text here"}
            ]
            result = await pipeline._build_attachment_context(attachments, query="machine learning")

        assert "full content provided below" in result
        assert "full document text here" in result

    @pytest.mark.asyncio
    async def test_fallback_on_retrieval_error(self):
        from reasoner.pipeline import ReasonerPipeline

        pipeline = ReasonerPipeline(
            router=MagicMock(),
            top_k=3,
            verbose=False,
            preset_name="auto-budget",
        )

        mock_store = MagicMock()
        mock_store.retrieve = AsyncMock(side_effect=Exception("embedder down"))

        with patch.object(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", True):
            with patch("reasoner.documents.vector_store.DocumentVectorStore", return_value=mock_store):
                attachments = [
                    {"file_id": "abc123", "filename": "paper.pdf", "extracted_text": "full document text here"}
                ]
                result = await pipeline._build_attachment_context(attachments, query="machine learning")

        assert "full content provided below" in result
        assert "full document text here" in result
