"""Cross-encoder reranking service for search and memory retrieval.

Supports Cohere Rerank models via OpenRouter (default) or direct Cohere API.
All functions gracefully degrade to returning documents unchanged on any error.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from typing import Any

import httpx

from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

# ── Constants ──
_MAX_QUERY_LENGTH = 10_000
_MAX_DOCUMENTS = 100
_MAX_DOC_LENGTH = 32_000
_RERANK_TIMEOUT_SECONDS = 15.0

# Track consecutive failures for lightweight circuit-breaking
_failure_count: int = 0
_failure_lock = asyncio.Lock()
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60.0
_last_failure_time: float = 0.0


def _sanitize_text(text: str, max_length: int = _MAX_QUERY_LENGTH) -> str:
    """Strip null bytes, normalize Unicode, truncate."""
    text = text.replace("\x00", "")
    try:
        text = unicodedata.normalize("NFKC", text)
    except Exception:
        pass
    return text[:max_length]


async def _is_circuit_open() -> bool:
    """Lightweight circuit breaker based on recent failures."""
    async with _failure_lock:
        global _failure_count, _last_failure_time
        if _failure_count < _CIRCUIT_THRESHOLD:
            return False
        elapsed = asyncio.get_event_loop().time() - _last_failure_time
        if elapsed >= _CIRCUIT_COOLDOWN_SECONDS:
            _failure_count = 0
            return False
        return True


async def _record_failure() -> None:
    async with _failure_lock:
        global _failure_count, _last_failure_time
        _failure_count += 1
        _last_failure_time = asyncio.get_event_loop().time()


async def _record_success() -> None:
    async with _failure_lock:
        global _failure_count
        _failure_count = 0


async def rerank_documents(
    query: str,
    documents: list[dict[str, Any]],
    top_n: int = 10,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
) -> list[dict[str, Any]]:
    """Rerank documents via cross-encoder (Cohere via OpenRouter by default).

    Args:
        query: The search query to rank against.
        documents: List of result dicts; each must have at least 'title' or 'content' or 'snippet'.
        top_n: How many top results to return.
        api_key: OpenRouter or Cohere API key. Defaults to OPENROUTER_API_KEY from settings.
        model: Rerank model ID. Defaults to COHERE_RERANK_MODEL from settings.
        api_base: API base URL. Defaults to OpenRouter.

    Returns:
        Documents reordered by relevance score, or unchanged on any error.
    """
    # ── Feature gating ──
    if not settings.COHERE_RERANK_ENABLED:
        return documents

    if len(documents) <= 1:
        return documents

    # ── Input validation ──
    query = _sanitize_text(query, _MAX_QUERY_LENGTH)
    if not query:
        return documents

    if len(documents) > _MAX_DOCUMENTS:
        documents = documents[:_MAX_DOCUMENTS]

    # ── Circuit breaker ──
    if await _is_circuit_open():
        logger.info("Rerank circuit open; skipping rerank.")
        return documents

    # ── Resolve credentials ──
    key = api_key or settings.OPENROUTER_API_KEY or ""
    if not key:
        return documents

    model_id = model or settings.COHERE_RERANK_MODEL or "cohere/rerank-4-fast"
    base = api_base or settings.RERANK_API_BASE

    # ── Build document texts ──
    texts: list[str] = []
    for doc in documents:
        title = doc.get("title", "")
        content = doc.get("content", "") or doc.get("snippet", "") or doc.get("body", "")
        combined = f"{title}\n{content}".strip() if title else content.strip()
        combined = _sanitize_text(combined, _MAX_DOC_LENGTH)
        texts.append(combined or " ")

    # ── Call rerank API ──
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
        "X-Title": settings.OPENROUTER_APP_TITLE,
    }
    payload = {
        "model": model_id,
        "query": query,
        "documents": texts,
        "top_n": min(top_n, len(texts)),
    }

    try:
        async with httpx.AsyncClient(timeout=_RERANK_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{base}/rerank", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        await _record_failure()
        logger.warning("Rerank API call failed: %s", exc)
        return documents

    # ── Reorder documents by rerank results ──
    results = data.get("results", [])
    if not results:
        await _record_failure()
        logger.warning("Rerank API returned empty results.")
        return documents

    indexed = {i: doc for i, doc in enumerate(documents)}
    reranked: list[dict[str, Any]] = []
    for r in results:
        idx = r.get("index")
        if idx in indexed:
            doc = indexed[idx]
            doc["rerank_score"] = r.get("relevance_score", 0.0)
            reranked.append(doc)

    await _record_success()
    logger.debug("Reranked %d documents, returned top %d", len(documents), len(reranked))
    return reranked


async def rerank_memory_chunks(
    query: str,
    chunks: list[Any],
    top_k: int = 5,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
) -> list[Any]:
    """Rerank memory chunks (ContextChunk objects) before compression.

    Args:
        query: The user's prompt.
        chunks: List of ContextChunk objects.
        top_k: How many top chunks to return.

    Returns:
        Chunks reordered by relevance, or unchanged on error.
    """
    if not settings.COHERE_RERANK_ENABLED:
        return chunks

    if len(chunks) <= 1:
        return chunks

    # Convert ContextChunks to plain dicts for the shared rerank function
    docs = [{"content": c.content, "source": c.source, "_chunk": c} for c in chunks]
    reranked_docs = await rerank_documents(
        query, docs, top_n=top_k, api_key=api_key, model=model, api_base=api_base
    )

    # Extract the original ContextChunk objects in new order
    result: list[Any] = []
    for d in reranked_docs:
        chunk = d.get("_chunk")
        if chunk:
            result.append(chunk)
    return result
