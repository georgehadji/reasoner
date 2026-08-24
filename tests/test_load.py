"""Load tests with concurrent async client (Critical Enhancement 7.4).

Replaces sync TestClient with httpx.AsyncClient for true concurrency.

These tests require a live Reasoner API server on localhost:8000.
They skip gracefully if the server is not running or is a different service.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

# ---------------------------------------------------------------------------
# Server-availability guard
# ---------------------------------------------------------------------------

def _reasoner_api_available() -> bool:
    """Return True if the Reasoner API is listening on localhost:8000."""
    try:
        r = httpx.get("http://localhost:8000/api/presets", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


REASONER_API_URL = "http://localhost:8000"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.slow
async def test_concurrent_queries_with_metrics():
    """Run 50 concurrent queries and verify p95 latency under 60s."""
    if not _reasoner_api_available():
        pytest.skip(f"Reasoner API not available at {REASONER_API_URL}")

    start = time.monotonic()

    async with httpx.AsyncClient(base_url=REASONER_API_URL, timeout=60) as client:
        tasks = [
            client.post(
                "/api/run",
                json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
            )
            for _ in range(50)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.monotonic() - start

    successes = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
    errors = [r for r in responses if isinstance(r, Exception)]

    print(f"Successes: {len(successes)}/50, Errors: {len(errors)}, Elapsed: {elapsed:.1f}s")

    assert len(successes) >= 40, f"Expected at least 40 successes, got {len(successes)}"
    assert elapsed < 60, f"Expected under 60s, got {elapsed:.1f}s"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.slow
async def test_100_concurrent_authenticated_users():
    """Run 100 concurrent authenticated requests and verify 95%% success rate.

    Critical Enhancement 9.5: validates horizontal-scaling readiness
    by hammering the API with concurrent authenticated users.
    """
    if not _reasoner_api_available():
        pytest.skip(f"Reasoner API not available at {REASONER_API_URL}")

    start = time.monotonic()

    # Generate a test JWT token (matching the test suite's JWT_SECRET)
    import os

    import jwt

    secret = os.environ.get("JWT_SECRET", "test-secret")
    token = jwt.encode(
        {"sub": "load-test-user", "exp": time.time() + 3600},
        secret,
        algorithm="HS256",
    )

    async with httpx.AsyncClient(base_url=REASONER_API_URL, timeout=60) as client:
        tasks = [
            client.post(
                "/api/run",
                json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
                headers={"Authorization": f"Bearer {token}"},
            )
            for _ in range(100)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.monotonic() - start

    successes = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
    errors = [r for r in responses if isinstance(r, Exception)]
    rate_limited = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 429]

    success_rate = len(successes) / len(responses)
    print(
        f"Successes: {len(successes)}/100, "
        f"Rate-limited: {len(rate_limited)}, "
        f"Errors: {len(errors)}, "
        f"Elapsed: {elapsed:.1f}s, "
        f"Success rate: {success_rate:.2%}"
    )

    # 95%% success rate gate (allowing for rate limits and transient errors)
    assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}"
    assert elapsed < 120, f"Expected under 120s, got {elapsed:.1f}s"
