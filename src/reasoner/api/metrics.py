"""
Prometheus metrics endpoints (FastAPI layer).

Metric definitions are in reasoner.metrics.py (shared module, no API deps).
This file contains only the FastAPI metrics endpoint + QueryTimer.
"""

from __future__ import annotations

import asyncio

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except Exception:
    def generate_latest(*args, **kwargs):
        return b""
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

from fastapi import Response

# Re-export all metrics from shared module
from reasoner.metrics import *  # noqa: F401, F403


async def metrics_endpoint() -> Response:
    """Expose Prometheus metrics.

    Critical Enhancement 7.2: generate_latest is synchronous,
    so we run it in a thread to avoid blocking the event loop.
    """
    content = await asyncio.to_thread(generate_latest)
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)


class QueryTimer:
    """Explicit timer for async pipeline execution (Critical Enhancement 7.1).

    Using `.time()` context manager on an async generator only measures
    until the first yield. This class records start time and exposes
    an explicit `observe()` call after the generator completes.
    """

    def __init__(self, preset: str):
        self.preset = preset
        self._start: float | None = None

    def start(self) -> None:
        self._start = time.monotonic()

    def observe(self) -> None:
        if self._start is not None:
            REASONER_QUERY_DURATION.labels(preset=self.preset).observe(
                time.monotonic() - self._start
            )
