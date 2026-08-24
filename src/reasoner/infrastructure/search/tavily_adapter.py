"""Tavily Search + Extract adapter — implements SearchServicePort.

Tavily provides structured search results (not just URLs) and an Extract
endpoint for fetching full content from URLs. Purpose-built for AI agents.

Cost: Free tier = 1,000 queries/month. No credit card required.
Latency: 180ms p50.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from reasoner.core.constants import TRUNCATION
from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

_TAVILY_SEARCH = "https://api.tavily.com/search"
_TAVILY_EXTRACT = "https://api.tavily.com/extract"


class TavilyAdapter:
    """Implements SearchServicePort for Tavily API.

    Graceful degradation: no API key → returns empty results.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.TAVILY_API_KEY
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search(
        self,
        query: str,
        num_results: int = 10,
        categories: list[str] | None = None,
        source_type: str | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._api_key:
            logger.debug("Tavily search skipped: no API key configured")
            return []

        try:
            client = await self._get_client()
            payload: dict[str, Any] = {
                "api_key": self._api_key,
                "query": query,
                "search_depth": "advanced" if num_results > 5 else "basic",
                "max_results": min(num_results, 20),
                "include_answer": False,
                "include_raw_content": False,
            }

            if source_type == "academic":
                payload["include_domains"] = [
                    "arxiv.org", "scholar.google.com", "pubmed.ncbi.nlm.nih.gov",
                    "nature.com", "sciencedirect.com", "ieee.org",
                ]
            elif source_type == "code":
                payload["include_domains"] = ["github.com", "stackoverflow.com", "gitlab.com"]
            elif source_type == "news":
                payload["topic"] = "news"

            resp = await client.post(_TAVILY_SEARCH, json=payload)
            resp.raise_for_status()
            data = resp.json()

            results: list[dict[str, Any]] = []
            for item in data.get("results", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": (item.get("content") or "")[:TRUNCATION.SNIPPET],
                    "snippet": (item.get("content") or "")[:TRUNCATION.SNIPPET],
                    "source": "tavily",
                    "full_content": item.get("raw_content", ""),
                    "published_date": item.get("published_date", ""),
                    "freshness_score": 0.6,
                })
            return results

        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []

    async def extract(
        self, urls: list[str]
    ) -> list[dict[str, Any]]:
        """Extract full content from URLs via Tavily Extract.

        Replaces Deep Read phase's per-URL scraping with a single API call.
        """
        if not self._api_key or not urls:
            return []

        try:
            client = await self._get_client()
            resp = await client.post(_TAVILY_EXTRACT, json={
                "api_key": self._api_key,
                "urls": urls,
            })
            resp.raise_for_status()
            data = resp.json()

            results: list[dict[str, Any]] = []
            for item in data.get("results", []):
                results.append({
                    "url": item.get("url", ""),
                    "content": item.get("raw_content", ""),
                    "title": item.get("title", ""),
                    "source": "tavily:extract",
                })
            return results

        except Exception as exc:
            logger.warning("Tavily extract failed: %s", exc)
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
