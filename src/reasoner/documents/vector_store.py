"""Per-session semantic vector store for uploaded documents.

Chunks uploaded file text, embeds via Neuro embedder, and retrieves
relevant passages via cosine similarity. Falls back gracefully to
verbatim injection when disabled or unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path
from typing import Any

from reasoner.core.settings import settings
from reasoner.uploader import UPLOAD_DIR

logger = logging.getLogger(__name__)

# ── Chunking defaults (overridable via settings) ──
_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 200
_MAX_CHUNKS_PER_FILE = 500
_MAX_TOTAL_RETRIEVE_CHUNKS = 20


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks.

    Args:
        text: Source text.
        size: Target chunk size in characters.
        overlap: Overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if not text:
        return []
    chunks: list[str] = []
    step = max(1, size - overlap)
    idx = 0
    while idx < len(text):
        end = idx + size
        chunk = text[idx:end]
        chunks.append(chunk)
        idx += step
        if len(chunks) >= _MAX_CHUNKS_PER_FILE:
            logger.warning("Document exceeded max chunks (%d); truncating.", _MAX_CHUNKS_PER_FILE)
            break
    return chunks


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class DocumentVectorStore:
    """Lightweight per-session vector store using JSON sidecars.

    No external DB dependency. Embeddings are stored as
    `{UPLOAD_DIR}/{file_id}.vectors.json`.
    """

    def __init__(self, embedder: Any | None = None):
        self._embedder = embedder
        self._lock = asyncio.Lock()

    def _get_embedder(self) -> Any:
        """Lazy-load Neuro embedder to avoid circular imports at module load."""
        if self._embedder is not None:
            return self._embedder
        try:
            from reasoner.neuro.config import load_config
            from reasoner.neuro.providers import create_resilient_embedding

            config = load_config()
            self._embedder = create_resilient_embedding(config.embedding)
            logger.info("DocumentVectorStore loaded embedder: %s", self._embedder.active_label)
        except Exception as exc:
            logger.warning("Failed to load Neuro embedder for document indexing: %s", exc)
            self._embedder = None
        return self._embedder

    def _sidecar_path(self, file_id: str) -> Path:
        return UPLOAD_DIR / f"{file_id}.vectors.json"

    async def index_file(
        self,
        file_id: str,
        text: str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """Chunk and embed a document, writing embeddings to a JSON sidecar.

        Args:
            file_id: The uploaded file's UUID.
            text: Extracted text content.
            chunk_size: Chunk size override.
            chunk_overlap: Overlap override.

        Returns:
            Number of chunks created.
        """
        embedder = self._get_embedder()
        if embedder is None:
            logger.warning("No embedder available; skipping document indexing for %s", file_id)
            return 0

        size = chunk_size or settings.DOCUMENT_CHUNK_SIZE or _DEFAULT_CHUNK_SIZE
        overlap = chunk_overlap or settings.DOCUMENT_CHUNK_OVERLAP or _DEFAULT_CHUNK_OVERLAP
        chunks = _chunk_text(text, size, overlap)
        if not chunks:
            return 0

        logger.info("Indexing %s into %d chunks (size=%d, overlap=%d)", file_id, len(chunks), size, overlap)

        # Embed chunks in parallel batches to avoid overwhelming the API
        batch_size = 8
        embeddings: list[list[float]] = []
        successful_chunks = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            try:
                batch_embeddings_raw = await asyncio.gather(
                    *[embedder.embed(chunk) for chunk in batch],
                    return_exceptions=True
                )
                for chunk, res in zip(batch, batch_embeddings_raw, strict=False):
                    if isinstance(res, BaseException):
                        logger.warning("Embedding chunk failed for %s: %s", file_id, res)
                    else:
                        embeddings.append(res)
                        successful_chunks.append(chunk)
            except Exception as exc:
                logger.warning("Embedding batch failed for %s: %s", file_id, exc)
                return 0

        chunks = successful_chunks

        sidecar = {
            "file_id": file_id,
            "chunk_count": len(chunks),
            "chunk_size": size,
            "chunk_overlap": overlap,
            "chunks": [
                {"text": chunk, "embedding": emb}
                for chunk, emb in zip(chunks, embeddings, strict=False)
            ],
        }

        try:
            from reasoner.security.encryption import get_encryption_service

            sidecar_json = json.dumps(sidecar, default=str)
            payload = get_encryption_service().encrypt(sidecar_json)
            self._sidecar_path(file_id).write_text(
                json.dumps({"encrypted": True, "payload": payload}), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to write vector sidecar for %s: %s", file_id, exc)
            return 0

        logger.info("Indexed %s: %d chunks embedded", file_id, len(chunks))
        return len(chunks)

    async def retrieve(
        self,
        query: str,
        file_ids: list[str],
        top_k: int = 5,
        user_id: str | None = None,
    ) -> list[str]:
        """Retrieve the top-k most relevant chunks for a query.

        Args:
            query: The search query (typically the user's problem/prompt).
            file_ids: List of uploaded file IDs to search.
            top_k: Number of chunks to return.

        Returns:
            List of chunk texts, ordered by relevance.
        """
        # Sidecars contain extracted user content.  Never retrieve them for an
        # unscoped request; callers without an authenticated owner can still
        # use the pipeline's explicit attachment fallback path.
        if not user_id:
            logger.warning("Refusing unscoped document-vector retrieval")
            return []

        from reasoner.infrastructure.uploader import _get_upload_meta

        authorized_file_ids = [
            fid for fid in file_ids
            if isinstance(fid, str)
            and (_get_upload_meta(fid) or {}).get("user_id") == user_id
        ]
        if not authorized_file_ids:
            return []

        embedder = self._get_embedder()
        if embedder is None:
            logger.warning("No embedder available; cannot retrieve document chunks.")
            return []

        # Load sidecars
        all_chunks: list[dict[str, Any]] = []
        for fid in authorized_file_ids:
            path = self._sidecar_path(fid)
            if not path.exists():
                logger.debug("No vector sidecar for %s", fid)
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("encrypted"):
                    from reasoner.security.encryption import get_encryption_service

                    sidecar = json.loads(get_encryption_service().decrypt(raw["payload"]))
                else:
                    # Legacy plaintext sidecar (no "encrypted" flag) -- read
                    # unchanged, no migration required.
                    sidecar = raw
                all_chunks.extend(sidecar.get("chunks", []))
            except Exception as exc:
                logger.warning("Failed to load sidecar for %s: %s", fid, exc)

        if not all_chunks:
            return []

        # Embed query
        try:
            query_embedding = await embedder.embed(query)
        except Exception as exc:
            logger.warning("Query embedding failed: %s", exc)
            return []

        # Score all chunks
        scored = []
        for chunk in all_chunks:
            emb = chunk.get("embedding")
            if not emb:
                continue
            score = _cosine_similarity(query_embedding, emb)
            scored.append((score, chunk["text"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        max_results = min(top_k, _MAX_TOTAL_RETRIEVE_CHUNKS)
        return [text for _, text in scored[:max_results]]

    def delete_index(self, file_id: str) -> bool:
        """Delete a document's vector sidecar."""
        path = self._sidecar_path(file_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as exc:
                logger.warning("Failed to delete sidecar for %s: %s", file_id, exc)
        return False
