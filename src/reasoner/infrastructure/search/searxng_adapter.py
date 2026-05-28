from __future__ import annotations
import httpx
import logging
from typing import Any, Optional

from reasoner.infrastructure.search.port import SourceType
from reasoner.core.constants import TIMEOUTS, DEFAULT_SEARXNG_URL
from reasoner.core.search import _should_include_result, _normalize_url, _parse_freshness, TRUNCATION

logger = logging.getLogger(__name__)

class SearXNGAdapter:
    def __init__(self, base_url: str = DEFAULT_SEARXNG_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=TIMEOUTS.SEARCH_CLIENT)

    async def _fetch_page(
        self,
        query: str,
        pageno: int,
        num_results: int,
        categories: Optional[list[str]],
        source_type: Optional[SourceType],
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Fetch one page of SearXNG results and apply the quality filter.

        Returns (refined_results, total_raw_fetched).
        """
        params: dict[str, Any] = {"q": query, "format": "json", "pageno": pageno}

        from reasoner.core.search import SOURCE_TYPE_ENGINES
        if source_type and source_type != "general":
            engines = SOURCE_TYPE_ENGINES.get(source_type, [])
            if engines:
                params["engines"] = ",".join(engines)

        if categories:
            params["categories"] = ",".join(categories)

        response = await self.client.get(f"{self.base_url}/search", params=params)
        response.raise_for_status()
        data = response.json()

        raw = data.get("results", [])
        refined: list[dict[str, Any]] = []
        seen_norm: set[str] = set()

        for r in raw:
            content = r.get("content", "")[:TRUNCATION.SNIPPET]
            freshness = _parse_freshness(r)
            result = {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": content,
                "snippet": content,
                "source": r.get("engine"),
                "full_content": r.get("content", ""),
                "published_date": r.get("publishedDate", ""),
                "freshness_score": freshness,
            }
            norm = _normalize_url(result.get("url", ""))
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            if _should_include_result(result):
                refined.append(result)
            else:
                logger.debug("Filtered out search result: %s", result.get("url"))

        return refined, len(raw)

    async def search(
        self,
        query: str,
        num_results: int = 10,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        from reasoner.core.search import _SEARXNG_CB
        if not await _SEARXNG_CB.can_execute():
            logger.warning(
                "SearXNG circuit breaker OPEN — skipping search for %r",
                query[:60],
            )
            return []

        if domain:
            query = f"site:{domain} {query}"

        try:
            refined, total_raw = await self._fetch_page(
                query, pageno=1, num_results=num_results,
                categories=categories, source_type=source_type,
            )

            _LOW_YIELD_THRESHOLD = min(3, max(1, num_results // 4))
            if len(refined) < _LOW_YIELD_THRESHOLD:
                logger.info(
                    "Page 1 low yield (%d results) for query=%r — fetching page 2",
                    len(refined), query[:80],
                )
                try:
                    page2, raw2 = await self._fetch_page(
                        query, pageno=2, num_results=num_results,
                        categories=categories, source_type=source_type,
                    )
                    existing_norms = {_normalize_url(r.get("url", "")) for r in refined}
                    new_from_p2 = [
                        r for r in page2
                        if _normalize_url(r.get("url", "")) not in existing_norms
                    ]
                    refined.extend(new_from_p2)
                    total_raw += raw2
                    logger.info("Page 2 added %d more results", len(new_from_p2))
                except Exception as p2_exc:
                    logger.debug("Page 2 fetch failed: %s", p2_exc)

            passed = len(refined)
            if total_raw > 0:
                logger.info(
                    "Search quality: %d/%d results passed filtering (%.0f%%) for query=%r",
                    passed, total_raw, (passed / total_raw) * 100, query[:80],
                )

            await _SEARXNG_CB.record_success()
            return refined[:num_results]

        except Exception as exc:
            await _SEARXNG_CB.record_failure()
            logger.error("Web discovery failed: %s", exc)
            return []
    
    async def close(self) -> None:
        await self.client.aclose()
