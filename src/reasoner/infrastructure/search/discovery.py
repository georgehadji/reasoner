"""
DiscoveryClient — multi-backend search client factory.

Extracted from core/search.py. Provides the `get_search_client` and
`get_search_client_for_method` factories used by research, article,
and search flow phases.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

from reasoner.core.ports.search_port import SearchServicePort, SourceType
from reasoner.core.constants import DEFAULT_SEARCH_RESULTS, TIMEOUTS, MODEL_QWEN35_9B, MODEL_QWEN35_FLASH, MODEL_GEMINI_FLASH
from reasoner.core.settings import settings


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




async def get_search_client_for_method(
    method: str = "multi_perspective",
    tier: str = "budget",
    source_type: Optional[SourceType] = None,
) -> tuple[Any, Optional[SourceType]]:
    """Return the best search client for a method+tier, trying backends in order.

    Tries the chain for the given method/tier (from SEARCH_METHOD_CHAINS) and
    returns the first working client. Falls back to existing Perplexity client
    if none of the new backends are configured.

    Args:
        method: Method name (multi_perspective, article, research, prism, direct).
        tier:  Price tier (budget, premium).
        source_type: Source type filter.

    Returns:
        (search_client, source_type) — same type as get_search_client().
    """
    from reasoner.core.constants_limits import SEARCH_METHOD_CHAINS
    from reasoner.core.settings import settings

    chain = SEARCH_METHOD_CHAINS.get(method, {}).get(tier, [])

    for backend in chain:
        if backend == "perplexity" or backend == "perplexity_deep":
            # Try Tavily/Brave when API keys are set.
            if settings.TAVILY_API_KEY and settings.TAVILY_SEARCH_ENABLED:
                from reasoner.infrastructure.search.tavily_adapter import TavilyAdapter
                return TavilyAdapter(), source_type
            if settings.BRAVE_SEARCH_API_KEY and settings.BRAVE_SEARCH_ENABLED:
                from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter
                return BraveSearchAdapter(), source_type
            # Fall back to Perplexity
            if settings.OPENROUTER_API_KEY:
                from reasoner.infrastructure.search.discovery import get_search_client
                return await get_search_client(source_type=source_type)

        elif backend == "brave":
            if settings.BRAVE_SEARCH_API_KEY and settings.BRAVE_SEARCH_ENABLED:
                from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter
                return BraveSearchAdapter(), source_type

        elif backend == "brave_llm":
            if settings.BRAVE_SEARCH_API_KEY and settings.BRAVE_SEARCH_ENABLED:
                from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter
                return BraveSearchAdapter(), source_type

        elif backend == "tavily":
            if settings.TAVILY_API_KEY and settings.TAVILY_SEARCH_ENABLED:
                from reasoner.infrastructure.search.tavily_adapter import TavilyAdapter
                return TavilyAdapter(), source_type

        elif backend == "openrouter_web":
            # Handled directly by the router/streaming layer — no adapter needed.
            # Return None to signal "use inline web_search parameter".
            return None, source_type

    # Ultimate fallback: existing Perplexity/get_search_client
    from reasoner.infrastructure.search.discovery import get_search_client
    return await get_search_client(source_type=source_type)


# ─────────────────────────────────────────────
#  SearXNG Adapter + DiscoveryClient
# ─────────────────────────────────────────────

class SearXNGAdapter:
    """Thin HTTP adapter for a single SearXNG instance."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def _fetch_page(
        self, query: str, params: dict | None = None
    ) -> tuple[list[dict], int]:
        import httpx
        url = f"{self._base_url}/search"
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(
                url,
                params={"q": query, "format": "json", **(params or {})},
            )
            resp.raise_for_status()
            data = resp.json()
        results: list[dict] = data.get("results", [])
        return results, len(results)


class DiscoveryClient:
    """Search client backed by SearXNG with circuit-breaker integration."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.adapter = SearXNGAdapter(base_url=self.base_url)

    async def search(self, query: str, **kwargs) -> list[dict]:
        import reasoner.core.search as _search_module
        cb = _search_module._SEARXNG_CB
        if cb is not None and not await cb.can_execute():
            return []
        try:
            results, _ = await self.adapter._fetch_page(query)
            if cb is not None:
                await cb.record_success()
            return results
        except Exception:
            if cb is not None:
                await cb.record_failure()
            return []

    async def close(self) -> None:
        pass


# ─────────────────────────────────────────────
#  SearXNG URL helpers
# ─────────────────────────────────────────────

def get_searxng_base_url() -> str:
    """Return SearXNG base URL (no trailing slash) from settings."""
    return settings.SEARXNG_URL.rstrip("/")


def get_searxng_urls() -> list[str]:
    """Return ordered list of SearXNG search URLs to try.

    Primary: from SEARXNG_URL setting.
    Secondary: hardcoded 127.0.0.1:8888 Docker-internal fallback.
    """
    base = get_searxng_base_url()
    return [f"{base}/search", "http://127.0.0.1:8888/search"]


# Module-level singleton for the default DiscoveryClient.
_discovery_client: "DiscoveryClient | None" = None


async def get_discovery_client(
    base_url: str | None = None,
    source_type: Optional[SourceType] = None,
) -> tuple["DiscoveryClient", Optional[SourceType]]:
    """Factory: return a DiscoveryClient for SearXNG.

    If *base_url* is given, always creates a fresh client with that URL.
    Otherwise returns (or lazily creates) the module-level singleton.
    """
    global _discovery_client
    if base_url is not None:
        return DiscoveryClient(base_url=base_url), source_type
    if _discovery_client is None:
        _discovery_client = DiscoveryClient(base_url=get_searxng_base_url())
    return _discovery_client, source_type


def reset_discovery_client() -> None:
    """Clear the module-level DiscoveryClient singleton (for testing)."""
    global _discovery_client
    _discovery_client = None


async def get_search_client(
    source_type: Optional[SourceType] = None,
) -> tuple[SearchClient, Optional[SourceType]]:
    """Factory: returns the best available search client.

    Tries Perplexity (via OpenRouter) first, then Tavily, then Brave.
    All backends gate on their API keys.
    """
    # Strategy 1: Perplexity via OpenRouter
    if settings.OPENROUTER_API_KEY:
        try:
            return PerplexitySearchClient(), source_type
        except ValueError:
            logger.warning("Perplexity client init failed — trying Tavily/Brave fallback")

    # Strategy 2: Tavily
    if settings.TAVILY_API_KEY and settings.TAVILY_SEARCH_ENABLED:
        from reasoner.infrastructure.search.tavily_adapter import TavilyAdapter
        return TavilyAdapter(), source_type

    # Strategy 3: Brave
    if settings.BRAVE_SEARCH_API_KEY and settings.BRAVE_SEARCH_ENABLED:
        from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter
        return BraveSearchAdapter(), source_type

    # Strategy 4: Return empty client — caller handles gracefully
    logger.warning("No search backend available — all API keys missing")
    return PerplexitySearchClient(), source_type