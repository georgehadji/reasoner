"""Encapsulates web discovery, search, and context vetting operations."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class SearchCacheEntry:
    """Single entry in the search result cache."""
    def __init__(self, results: list[dict[str, Any]], expires_at: float):
        self.results = results
        self.expires_at = expires_at


class SearchService:
    """Service for web search, discovery, and context vetting.

    Features a 60s TTL in-memory cache (256 entry max) to avoid redundant
    external API calls when the same query is issued for multiple phases
    within a single pipeline run.
    """

    def __init__(self) -> None:
        self._cache: dict[str, SearchCacheEntry] = {}
        self._cache_ttl: float = 60.0
        self._cache_max_entries: int = 256

    def _cache_key(self, query: str, source_type: str, num_results: int) -> str:
        return hashlib.sha256(
            f"{query}:{source_type}:{num_results}".encode()
        ).hexdigest()[:32]

    def _prune_expired(self) -> None:
        """Remove expired entries from the cache."""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now >= v.expires_at]
        for k in expired:
            del self._cache[k]

    def _cache_get(self, key: str) -> list[dict[str, Any]] | None:
        """Return cached results or None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() >= entry.expires_at:
            del self._cache[key]
            return None
        return entry.results

    def _cache_set(self, key: str, results: list[dict[str, Any]]) -> None:
        """Store results in cache, evicting oldest if over capacity."""
        self._prune_expired()
        # Evict oldest if at capacity
        if len(self._cache) >= self._cache_max_entries:
            oldest = min(self._cache.keys(), key=lambda k: self._cache[k].expires_at)
            del self._cache[oldest]
        self._cache[key] = SearchCacheEntry(
            results=results,
            expires_at=time.time() + self._cache_ttl,
        )

    async def search(
        self,
        query: str,
        source_type: str = "general",
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Execute a standalone web search (for /api/search and streaming).

        Results are cached in-memory for 60s to avoid redundant API calls
        when the same query is issued for multiple phases (e.g., research +
        verification within one pipeline run).
        """
        cache_key = self._cache_key(query, source_type, num_results)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Search cache HIT for query=%s", query[:40])
            return cached

        from reasoner.core.search import get_search_client

        try:
            client, _ = await get_search_client(source_type=source_type)
            results = await client.search(query, num_results=num_results, source_type=source_type)
            self._cache_set(cache_key, results)
            return results
        except Exception as exc:
            logger.warning("Search failed: %s", exc)
            return []

    async def stream_web_search_results(
        self,
        problem: str,
        run_id: str,
        num_results: int = 10,
        cancel_event: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream web search results as a virtual single-phase pipeline.

        Results are fetched via the configured search client (Perplexity via
        OpenRouter when OPENROUTER_API_KEY is set, otherwise Tavily/Brave).
        """
        from reasoner.application.services.serializers import _event
        import time

        yield _event({"type": "start"})

        if cancel_event and cancel_event.is_set():
            yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
            return

        yield _event({"type": "phase_start", "phase": 0, "name": "Web Search"})
        phase_start = time.monotonic()
        results = await self.search(problem, source_type="general", num_results=num_results)
        duration = time.monotonic() - phase_start

        if not results:
            data = {
                "solution": "No relevant web search results were found for your query.",
                "tokens": {"input": 0, "output": 0},
                "duration": duration,
            }
            yield _event({
                "type": "phase_complete",
                "phase": 0,
                "name": "Web Search",
                "data": data,
            })
            yield _event({
                "type": "done",
                "errors": [],
                "total_tokens": {"input": 0, "output": 0, "total": 0},
                "duration": duration,
            })
            return

        md_lines = ["### Web Search Results\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title") or "Untitled"
            url = r.get("url") or ""
            snippet = r.get("snippet") or r.get("content") or ""
            md_lines.append(f"{i}. [{title}]({url})")
            if snippet:
                md_lines.append(f"   > {snippet}")
            md_lines.append("")

        solution = "\n".join(md_lines).strip()
        data = {
            "solution": solution,
            "tokens": {"input": 0, "output": 0},
            "duration": duration,
        }
        yield _event({
            "type": "phase_complete",
            "phase": 0,
            "name": "Web Search",
            "data": data,
        })
        yield _event({
            "type": "done",
            "errors": [],
            "total_tokens": {"input": 0, "output": 0, "total": 0},
            "duration": duration,
        })

    async def close(self) -> None:
        """No-op — kept for interface compatibility.

        Previously reset a cached search-client singleton.
        `get_search_client()` builds a fresh client per call, so there is
        nothing to tear down here.
        """
        return None
