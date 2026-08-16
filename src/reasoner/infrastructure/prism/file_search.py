"""FileSearchPort implementation using Neuro embeddings and uploaded file sidecars."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from reasoner.core.ports.file_search_port import FileSearchPort, FileChunk
from reasoner.infrastructure.uploader import UPLOAD_DIR

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class PrismFileSearch(FileSearchPort):
    """Searches uploaded file chunks by semantic similarity."""

    def __init__(self, embedder: Any | None = None):
        self._embedder = embedder

    def _get_embedder(self) -> Any:
        """Lazy-load Neuro embedder to avoid circular imports at module load."""
        if self._embedder is not None:
            return self._embedder
        try:
            from reasoner.neuro.config import load_config
            from reasoner.neuro.providers import create_resilient_embedding

            config = load_config()
            self._embedder = create_resilient_embedding(config.embedding)
            logger.info("PrismFileSearch loaded embedder: %s", getattr(self._embedder, "active_label", "unknown"))
        except Exception as exc:
            logger.warning("Failed to load Neuro embedder for file search: %s", exc)
            self._embedder = None
        return self._embedder

    def _sidecar_path(self, file_id: str) -> Path:
        return UPLOAD_DIR / f"{file_id}.vectors.json"

    async def search_chunks(
        self,
        file_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[FileChunk]:
        embedder = self._get_embedder()
        if embedder is None:
            logger.debug("No embedder available; skipping file search.")
            return []

        # Embed query
        try:
            query_embedding = await embedder.embed(query)
        except Exception as exc:
            logger.warning("Query embedding failed: %s", exc)
            return []

        # Load sidecars and score
        scored: list[tuple[float, str, str]] = []
        for fid in file_ids:
            path = self._sidecar_path(fid)
            if not path.exists():
                logger.debug("No vector sidecar for %s", fid)
                continue
            try:
                sidecar = json.loads(path.read_text(encoding="utf-8"))
                for chunk in sidecar.get("chunks", []):
                    emb = chunk.get("embedding")
                    text = chunk.get("text", "")
                    if emb and text:
                        score = _cosine_similarity(query_embedding, emb)
                        scored.append((score, fid, text))
            except Exception as exc:
                logger.warning("Failed to load sidecar for %s: %s", fid, exc)

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            FileChunk(file_id=fid, content=text, score=score)
            for score, fid, text in scored[:top_k]
        ]
