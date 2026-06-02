"""
DiscoveryClient — wraps SearXNGAdapter for web search.

Extracted from core/search.py. Provides the `get_discovery_client` factory
function used by research, article, and search flow phases.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Protocol

from reasoner.core.ports.search_port import SearchServicePort, SourceType
from reasoner.core.constants import DEFAULT_SEARCH_RESULTS, DEFAULT_SEARXNG_URL, TIMEOUTS, MODEL_QWEN35_9B, MODEL_QWEN35_FLASH, MODEL_GEMINI_FLASH
from reasoner.infrastructure.search.searxng_adapter import SearXNGAdapter

# DiscoveryClient now wraps SearXNGAdapter to conform to SearchServicePort
class DiscoveryClient(SearchServicePort):
    def __init__(self, base_url: str = DEFAULT_SEARXNG_URL):
        self.adapter = SearXNGAdapter(base_url=base_url)

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return await self.adapter.search(
            query, num_results, categories, source_type, domain
        )

    async def close(self) -> None:
        await self.adapter.close()


# ─────────────────────────────────────────────
#  Perplexity Search Client (Strategy Pattern)
# ─────────────────────────────────────────────

class PerplexitySearchClient:
    """Search client using Perplexity Sonar via OpenRouter.

    Returns synthesized results with citations.
    Falls back to empty list on any error.
    """

    def __init__(self, model_id: str = "sonar") -> None:
        build_provider = _get_build_provider()
        self.provider = build_provider(model_id)

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        try:
            kwargs: dict[str, Any] = {
                "model": self.provider.model,
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 2048,
            }
            if getattr(self.provider, "extra_body", None):
                kwargs["extra_body"] = self.provider.extra_body

            response = await self.provider.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            citations = getattr(response, "citations", [])

            url = (citations[0] or "") if citations else ""
            if not url:
                # Perplexity via OpenRouter often returns empty citations.
                # Use a synthetic URL so the result isn't dropped by downstream filters.
                url = f"perplexity://synthetic/{query[:40].replace(' ', '_')}"
            return [{
                "title": f"Perplexity result for: {query[:50]}",
                "url": url,
                "content": content,
                "snippet": content[:TRUNCATION.SNIPPET],
                "source": "perplexity",
                "source_type": "synthetic",
                "citations": citations,
                "freshness_score": 1.0,
            }]
        except Exception as e:
            logger.error("Perplexity search via OpenRouter failed: %s", e)
            return []

    async def close(self):
        pass


class SearchClient(Protocol):
    """Protocol for search clients (Strategy Pattern)."""

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]: ...

    async def close(self): ...


_default_client: Optional[DiscoveryClient] = None


def reset_discovery_client() -> None:
    """Reset the global discovery client. Call this if base_url changes."""
    global _default_client
    old = _default_client
    _default_client = None
    if old is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old.close())
        except RuntimeError:
            try:
                asyncio.run(old.close())
            except Exception:
                pass


# ─────────────────────────────────────────────
#  Query Decomposition
# ─────────────────────────────────────────────

_DECOMPOSITION_MODELS = [MODEL_QWEN35_9B, MODEL_QWEN35_FLASH, MODEL_GEMINI_FLASH]

_DECOMPOSITION_CACHE: dict[str, tuple[list[str], float]] = {}
_DECOMPOSITION_TTL_SECONDS = 300.0
_MAX_DECOMPOSITION_CACHE_SIZE = 512


def _prune_decomposition_cache() -> None:
    excess = len(_DECOMPOSITION_CACHE) - _MAX_DECOMPOSITION_CACHE_SIZE
    if excess > 0:
        sorted_items = sorted(_DECOMPOSITION_CACHE.items(), key=lambda item: item[1][1])
        for key, _ in sorted_items[:excess]:
            del _DECOMPOSITION_CACHE[key]


def _extract_search_keywords(text: str, max_keywords: int = 8) -> str:
    """
    Extract English keywords from mixed-language prompts using regex.
    Returns a space-separated keyword string suitable for search.
    """
    words = _KEYWORD_RE.findall(text)
    cleaned = []
    for w in words:
        w = w.lower().strip("-")
        if len(w) > 2 and w not in _STOP_WORDS:
            cleaned.append(w)
    seen: set[str] = set()
    unique = [w for w in cleaned if not (w in seen or seen.add(w))]
    return " ".join(unique[:max_keywords])


async def _decompose_query(query: str, model_id: str | None = None) -> list[str]:
    """Use a lightweight LLM to break a query into 2-3 focused sub-queries."""
    now = time.monotonic()
    cached = _DECOMPOSITION_CACHE.get(query)
    if cached is not None:
        sub_queries, ts = cached
        if now - ts < _DECOMPOSITION_TTL_SECONDS:
            logger.debug("Decomposition cache hit for query: %r", query[:80])
            return sub_queries
        _DECOMPOSITION_CACHE.pop(query, None)

    system_prompt = (
        "You are a search assistant. Given a user query, break it into 2-3 focused, "
        "standalone search queries that together cover the user's intent. "
        "Output ONLY a JSON array of strings. Do not include markdown, explanations, "
        "or code blocks.\n"
        'Example: ["query 1", "query 2"]'
    )
    build_provider = _get_build_provider()
    provider = build_provider(model_id or _DECOMPOSITION_MODELS[0])
    raw = await provider.complete_with_retry(
        system_prompt=system_prompt,
        user_prompt=query,
        max_tokens=TRUNCATION.SNIPPET,
        temperature=NON_PHASE_TEMPERATURES["search_query_generation"],
    )
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[-1].strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Decomposition JSON parse failed for query: %s", query)
        arr = []
    if not isinstance(arr, list):
        raise ValueError("LLM did not return a JSON array")
    result = [str(item).strip() for item in arr if str(item).strip()]
    result = result[:DEFAULT_MAX_DECOMPOSED_QUERIES]

    _DECOMPOSITION_CACHE[query] = (result, now)
    _prune_decomposition_cache()
    return result


# ─────────────────────────────────────────────
#  Smart Search (with BM25 re-ranking)
# ─────────────────────────────────────────────

async def smart_search(
    query: str,
    source_type: Optional[SourceType] = None,
    num_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Decompose the query via a cheap LLM, run parallel searches,
    deduplicate by normalised URL, BM25-rank by relevance + freshness,
    and return the top N results.

    Falls back to a single keyword-extracted search on decomposition failure.
    """
    client, _ = await get_search_client(source_type=source_type)

    sub_queries: list[str] = []
    last_error: Exception | None = None
    for model_id in _DECOMPOSITION_MODELS:
        try:
            sub_queries = await _decompose_query(query, model_id=model_id)
            if sub_queries:
                break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Smart search decomposition with %s failed (%s). Trying fallback LLM. Raw query: %r",
                model_id, exc, query,
            )

    if not sub_queries:
        logger.warning(
            "Smart search decomposition failed for all LLMs (last error: %s). "
            "Raw query: %r. Falling back to keyword extraction + direct search.",
            last_error, query,
        )
        keyword_query = _extract_search_keywords(query)
        fallback_query = keyword_query if keyword_query else query
        results = await client.search(fallback_query, num_results=num_results, source_type=source_type)
        results.sort(key=lambda r: _bm25_score(query, r), reverse=True)
        return results

    per_query = max(3, num_results // len(sub_queries))

    async def _search_one(q: str) -> tuple[str, list[dict[str, Any]]]:
        results = await client.search(q, num_results=per_query, source_type=source_type)
        return q, results

    tasks = [_search_one(q) for q in sub_queries]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    seen_norms: set[str] = set()
    grouped_results: list[dict[str, Any]] = []

    for item in gathered:
        if isinstance(item, Exception):
            logger.warning("Smart search sub-query failed: %s", item)
            continue
        q, results = item
        for r in results:
            norm = _normalize_url(r.get("url", ""))
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)
            grouped_results.append({**r, "group": q})

    if not grouped_results:
        keyword_query = _extract_search_keywords(query)
        fallback_query = keyword_query if keyword_query else query
        results = await client.search(fallback_query, num_results=num_results, source_type=source_type)
        results.sort(key=lambda r: _bm25_score(query, r), reverse=True)
        return results

    # Re-rank by composite BM25 relevance + freshness before returning
    def _composite_score(r: dict) -> float:
        bm25 = _bm25_score(query, r)
        freshness = r.get("freshness_score", 0.5)
        return bm25 * 0.8 + freshness * 0.2

    grouped_results.sort(key=_composite_score, reverse=True)
    top_candidates = grouped_results[:num_results * 2]

    # Optional: cross-encoder rerank for higher precision
    if settings.COHERE_RERANK_ENABLED and len(top_candidates) > 1:
        try:
            reranked = await rerank_documents(query, top_candidates, top_n=num_results)
            if len(reranked) >= num_results:
                return reranked[:num_results]
        except Exception as exc:
            logger.warning("Rerank step failed in smart_search: %s", exc)

    return top_candidates[:num_results]


# ─────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────

def get_searxng_urls() -> list[str]:
    """Return the list of SearXNG URLs to try, respecting SEARXNG_URL env var."""
    base = settings.SEARXNG_URL.rstrip("/")
    urls = [f"{base}/search"]
    # Always include fallback to 127.0.0.1:8888 (default SearXNG port)
    # If base already uses localhost, also include IP version
    if "localhost" in base:
        ip_base = base.replace("localhost", "127.0.0.1")
        urls.append(f"{ip_base}/search")
    else:
        # Include default IP fallback regardless of custom URL
        fallback_base = DEFAULT_SEARXNG_URL.replace("localhost", "127.0.0.1")
        urls.append(f"{fallback_base}/search")
    return urls


def get_searxng_base_url() -> str:
    """Return the configured SearXNG base URL."""
    return settings.SEARXNG_URL.rstrip("/")


async def get_discovery_client(
    base_url: str | None = None,
    source_type: Optional[SourceType] = None,
) -> tuple[DiscoveryClient, Optional[SourceType]]:
    """Get or create the shared discovery client."""
    global _default_client
    resolved_base = (base_url or get_searxng_base_url()).rstrip("/")
    
    if _default_client is not None and _default_client.base_url != resolved_base:
        reset_discovery_client()

    if _default_client is None:
        _default_client = DiscoveryClient(base_url=resolved_base)
    return _default_client, source_type


async def get_search_client(
    source_type: Optional[SourceType] = None,
) -> tuple[SearchClient, Optional[SourceType]]:
    """Factory: returns SearXNG when healthy, Perplexity when SearXNG is down or
    when OpenRouter key is available and SearXNG fails."""
    searxng_healthy = await _SEARXNG_CB.can_execute()

    # Strategy 1: SearXNG is healthy — try it first for raw source diversity
    if searxng_healthy:
        try:
            client, resolved_type = await get_discovery_client(source_type=source_type)
            # Quick health check: perform a lightweight search
            health_results = await client.search("test", num_results=1)
            # Must return at least one result to be considered truly healthy
            if health_results:
                return client, resolved_type
            logger.warning("SearXNG health check returned 0 results — considering fallback")
        except Exception as exc:
            logger.warning("SearXNG health check failed (%s) — considering fallback", exc)

    # Strategy 2: SearXNG is down or unhealthy — use Perplexity if available
    if settings.OPENROUTER_API_KEY:
        logger.info("SearXNG circuit OPEN/unhealthy/empty — using Perplexity fallback")
        try:
            return PerplexitySearchClient(), source_type
        except ValueError:
            logger.warning("Perplexity client init failed — falling back to SearXNG")

    # Strategy 3: Last resort — return SearXNG even if circuit breaker suggests it's open.
    # The caller's error handling will deal with actual failures.
    return await get_discovery_client(source_type=source_type)