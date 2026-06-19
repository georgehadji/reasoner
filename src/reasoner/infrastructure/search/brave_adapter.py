"""Brave Search API adapter — implements SearchServicePort.

Uses Brave Search API (api.search.brave.com/res/v1/web/search) with
the LLM Context endpoint for RAG-optimized snippets.

Cost: $5/1K queries. 1K free/month.
Rate limits: 50 queries/second.
Independent search index (not Google/Bing reseller).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from reasoner.core.settings import settings
from reasoner.core.constants import TRUNCATION

logger = logging.getLogger(__name__)

_BRAVE_BASE = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_LLM_BASE = "https://api.search.brave.com/res/v1/web/llm_context"


class BraveSearchAdapter:
    """Implements SearchServicePort for Brave Search API.

    Graceful degradation: no API key → returns empty results.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.BRAVE_SEARCH_API_KEY
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
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
            logger.debug("Brave Search skipped: no API key configured")
            return []

        try:
            client = await self._get_client()
            count = min(num_results, 20)

            # Build params
            params: dict[str, Any] = {
                "q": query,
                "count": count,
                "freshness": "py" if source_type == "news" else "p3m",
            }

            # Source-type filtering via query augmentation
            if source_type == "academic":
                params["q"] = f"{query} site:arxiv.org OR site:scholar.google.com"
            elif source_type == "code":
                params["q"] = f"{query} site:github.com OR site:stackoverflow.com"
            elif source_type == "social":
                params["freshness"] = "pw"

            headers = {
                "X-Subscription-Token": self._api_key,
                "Accept": "application/json",
            }

            resp = await client.get(_BRAVE_BASE, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            results: list[dict[str, Any]] = []
            web = data.get("web", {})
            for item in web.get("results", [])[:num_results]:
                freshness_score = 0.5
                age = item.get("age", "")
                if age:
                    if "hour" in age:
                        freshness_score = 1.0
                    elif "day" in age:
                        freshness_score = 0.9
                    elif "week" in age:
                        freshness_score = 0.7
                    elif "month" in age:
                        freshness_score = 0.5

                brave_type = item.get("type", "")
                source = {"brave": 1.0}.get(brave_type, 0.5)

                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": (item.get("description") or "")[:TRUNCATION.SNIPPET],
                    "snippet": (item.get("description") or "")[:TRUNCATION.SNIPPET],
                    "source": f"brave:{brave_type}",
                    "full_content": "",
                    "published_date": item.get("age", ""),
                    "freshness_score": freshness_score,
                })

            return results

        except httpx.HTTPStatusError as exc:
            logger.warning("Brave Search API error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Brave Search failed: %s", exc)
            return []

    async def llm_context(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        """Fetch RAG-optimised context snippets via Brave's LLM Context endpoint.

        Returns a shorter list with richer content. Used by Article and Research
        methods that need more substantive source material.
        """
        if not self._api_key:
            return []

        try:
            client = await self._get_client()
            headers = {
                "X-Subscription-Token": self._api_key,
                "Accept": "application/json",
            }
            resp = await client.get(
                _BRAVE_LLM_BASE,
                params={"q": query},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[dict[str, Any]] = []
            for item in data.get("results", [])[:5]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": (item.get("description") or "")[:4096],
                    "snippet": (item.get("description") or "")[:2048],
                    "source": "brave:llm_context",
                    "full_content": item.get("long_description", ""),
                    "published_date": item.get("age", ""),
                    "freshness_score": 0.8,
                })
            return results

        except Exception as exc:
            logger.warning("Brave LLM Context failed: %s", exc)
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
