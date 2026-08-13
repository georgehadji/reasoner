"""Cross-encoder reranking service for search and memory retrieval.

Supports Cohere Rerank models via OpenRouter (default) or direct Cohere API.
All functions gracefully degrade to returning documents unchanged on any error.
"""

from __future__ import annotations

import asyncio
import logging
import math
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
        elapsed = asyncio.get_running_loop().time() - _last_failure_time
        if elapsed >= _CIRCUIT_COOLDOWN_SECONDS:
            _failure_count = 0
            return False
        return True


async def _record_failure() -> None:
    async with _failure_lock:
        global _failure_count, _last_failure_time
        _failure_count += 1
        _last_failure_time = asyncio.get_running_loop().time()


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
    # If Nemotron is the primary reranker, delegate entirely.
    if settings.NEMOTRON_RERANK_ENABLED:
        return await rerank_via_nemotron(
            query, documents, top_n=top_n, api_key=api_key, api_base=api_base
        )

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
        logger.warning("Cohere rerank failed (%s); falling back to Nemotron reranker.", exc)
        return await _rerank_fallback(query, documents, top_n, api_key, api_base)

    # ── Reorder documents by rerank results ──
    results = data.get("results", [])
    if not results:
        await _record_failure()
        logger.warning("Cohere rerank returned empty results; falling back to Nemotron reranker.")
        return await _rerank_fallback(query, documents, top_n, api_key, api_base)

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


async def _rerank_fallback(
    query: str,
    documents: list[dict[str, Any]],
    top_n: int,
    api_key: str | None,
    api_base: str | None,
) -> list[dict[str, Any]]:
    """Secondary reranker, used only when explicitly enabled.

    The Nemotron path scores each document with its own chat request. Its default
    model is a removed endpoint, so running it unconditionally after a Cohere
    failure spent one request per document on a dead URL, waited out the timeout on
    each, and then stamped every document with the neutral 0.5 error score — worse
    than not reranking at all. Reranking is an optional precision boost, so the
    correct degraded behaviour is to return the documents untouched.
    """
    if not settings.NEMOTRON_RERANK_ENABLED:
        logger.info("Rerank unavailable; returning documents unranked.")
        return documents
    return await rerank_via_nemotron(
        query, documents, top_n=top_n, api_key=api_key, api_base=api_base
    )


async def _score_document_nemotron(
    query: str,
    document_text: str,
    model: str,
    api_key: str,
    api_base: str,
    semaphore: asyncio.Semaphore,
) -> float:
    """Score a single document against a query using Nemotron Rerank VL via logprobs.

    The model is discriminative — it does not generate text. Relevance is read from
    the log-probability of the positive token ("Yes") in the first output position.
    Returns a float in [0, 1]; returns 0.5 on any error (neutral/unknown relevance).
    """
    prompt = (
        "Given the following query and document, determine whether the document is relevant "
        "to answering the query.\n\n"
        f"Query: {query}\n\n"
        f"Document: {document_text}\n\n"
        "Is this document relevant to the query? Answer with a single word."
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1,
        "temperature": 0.0,
        "logprobs": True,
        "top_logprobs": 5,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
        "X-Title": settings.OPENROUTER_APP_TITLE,
    }
    async with semaphore:
        try:
            async with httpx.AsyncClient(timeout=_RERANK_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.debug("Nemotron score call failed: %s", exc)
            return 0.5  # neutral on error

    # Extract logprob for "Yes" from the top_logprobs of the first output token
    try:
        top_logprobs: list[dict] = (
            data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        )
        for entry in top_logprobs:
            token = entry.get("token", "").strip().lower()
            if token in ("yes", "yes.", "true", "1", "relevant"):
                return min(1.0, max(0.0, math.exp(entry["logprob"])))
        # If "Yes" is not in top-5, the model is confident in "No" — return low score
        return 0.05
    except (KeyError, IndexError, TypeError):
        return 0.5


async def rerank_via_nemotron(
    query: str,
    documents: list[dict[str, Any]],
    top_n: int = 10,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
) -> list[dict[str, Any]]:
    """Rerank documents using NVIDIA Nemotron Rerank VL (free, via OpenRouter).

    Unlike Cohere's dedicated /rerank endpoint, Nemotron uses the chat completions
    API with logprobs. Each document is scored in a separate request, run in parallel
    with bounded concurrency (NEMOTRON_RERANK_CONCURRENCY, default 5).

    Use cases in Reasoner:
    - Search result reranking (context vetting phase, Phase 1.25)
    - Neuro memory chunk selection before compression (L3 recall)
    - Fallback when Cohere rerank is unavailable or disabled
    - Multimodal document queries (supports text+image VL inputs)

    Args:
        query: The query to rank documents against.
        documents: List of result dicts with 'title', 'content', or 'snippet' keys.
        top_n: How many top results to return after reranking.
        api_key: OpenRouter API key (falls back to OPENROUTER_API_KEY).
        model: Override the default Nemotron model.
        api_base: Override the default OpenRouter base URL.

    Returns:
        Documents sorted by descending relevance score, truncated to top_n.
        Each document gets a 'rerank_score' float added.
        Returns input unchanged on any global failure.
    """
    if len(documents) <= 1:
        return documents

    key = api_key or settings.OPENROUTER_API_KEY or ""
    if not key:
        logger.debug("Nemotron rerank skipped: no API key available.")
        return documents

    model_id = model or settings.NEMOTRON_RERANK_MODEL
    if not model_id:
        logger.warning(
            "Secondary reranker requested but NEMOTRON_RERANK_MODEL is unset; "
            "returning documents unranked. Set it to a live logprobs-capable model."
        )
        return documents
    base = api_base or settings.RERANK_API_BASE
    concurrency = settings.NEMOTRON_RERANK_CONCURRENCY

    query = _sanitize_text(query, _MAX_QUERY_LENGTH)
    if not query:
        return documents

    docs = documents[:_MAX_DOCUMENTS]

    semaphore = asyncio.Semaphore(concurrency)

    async def _score(doc: dict[str, Any]) -> tuple[dict[str, Any], float]:
        title = doc.get("title", "")
        content = doc.get("content", "") or doc.get("snippet", "") or doc.get("body", "")
        text = f"{title}\n{content}".strip() if title else content.strip()
        text = _sanitize_text(text, _MAX_DOC_LENGTH)
        score = await _score_document_nemotron(query, text or " ", model_id, key, base, semaphore)
        return doc, score

    results_raw = await asyncio.gather(
        *[_score(d) for d in docs],
        return_exceptions=True,
    )
    
    results: list[tuple[dict[str, Any], float]] = []
    for res in results_raw:
        if isinstance(res, BaseException):
            logger.warning("Nemotron rerank task failed: %s", res)
        else:
            results.append(res)
            
    if not results:
        return documents

    scored = sorted(results, key=lambda t: t[1], reverse=True)
    reranked: list[dict[str, Any]] = []
    for doc, score in scored[:top_n]:
        doc = dict(doc)
        doc["rerank_score"] = score
        reranked.append(doc)

    logger.debug(
        "Nemotron reranked %d → top %d (top score: %.3f)",
        len(docs),
        len(reranked),
        reranked[0]["rerank_score"] if reranked else 0.0,
    )
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
    if not settings.COHERE_RERANK_ENABLED and not settings.NEMOTRON_RERANK_ENABLED:
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
