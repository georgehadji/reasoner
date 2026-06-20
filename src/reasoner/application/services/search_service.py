"""Encapsulates web discovery, search, and context vetting operations."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class SearchService:
    """Service for web search, discovery, and context vetting."""

    async def search(
        self,
        query: str,
        source_type: str = "general",
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Execute a standalone web search (for /api/search and streaming)."""
        from reasoner.core.search import get_search_client

        try:
            client, _ = await get_search_client(source_type=source_type)
            return await client.search(query, num_results=num_results, source_type=source_type)
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
        OpenRouter when OPENROUTER_API_KEY is set, otherwise SearXNG).
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
        """Close discovery client."""
        from reasoner.infrastructure.search.discovery import reset_discovery_client

        reset_discovery_client()
