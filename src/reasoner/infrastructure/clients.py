"""
Shared HTTP clients with connection pooling.

Reduces TCP handshake overhead for internal service calls.
"""

from __future__ import annotations

import httpx

_neuro_client: httpx.AsyncClient | None = None


async def close_neuro_client() -> None:
    """Close the shared Neuro HTTP client (called once on shutdown)."""
    global _neuro_client
    if _neuro_client is not None:
        await _neuro_client.aclose()
        _neuro_client = None


def get_neuro_client() -> httpx.AsyncClient:
    """Get or create a shared AsyncClient for Neuro endpoints."""
    global _neuro_client
    if _neuro_client is None:
        _neuro_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
            timeout=httpx.Timeout(30.0),
        )
    return _neuro_client
