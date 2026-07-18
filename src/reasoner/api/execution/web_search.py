"""Web search streaming execution."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from reasoner.application.services.search_service import SearchService

_search_service = SearchService()


async def _stream_web_search_results(
    problem: str,
    run_id: str,
    num_results: int = 10,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Stream web search results as a virtual single-phase pipeline."""
    async for chunk in _search_service.stream_web_search_results(
        problem, run_id, num_results=num_results, cancel_event=cancel_event
    ):
        yield chunk
