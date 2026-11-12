"""perf audit LI-02: the direct OpenAI-compatible fallback lane reuses one pool.

It built a new httpx.AsyncClient per call, so every fallback call paid a TCP+TLS
handshake. It now goes through OpenAICompatibleProvider.shared_pool().
"""

from __future__ import annotations

import httpx
import pytest

from reasoner.infrastructure.llm.providers.direct import OpenAICompatibleDirectProvider
from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider

pytestmark = pytest.mark.unit


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})


async def test_calls_reuse_the_shared_pool(monkeypatch):
    pool = httpx.AsyncClient(transport=httpx.MockTransport(_ok))
    monkeypatch.setattr(OpenAICompatibleProvider, "_shared_pool", pool)
    made: list[object] = []
    real = httpx.AsyncClient.__init__

    def spy(self, *a, **k):
        made.append(self)
        real(self, *a, **k)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy)
    provider = OpenAICompatibleDirectProvider("k", "m", "http://x/v1")

    assert await provider.complete("s", "u") == "hi"
    assert await provider.complete("s", "u") == "hi"

    assert made == []
    assert not pool.is_closed
    await pool.aclose()


async def test_shared_pool_returns_one_client(monkeypatch):
    monkeypatch.setattr(OpenAICompatibleProvider, "_shared_pool", None)

    a = OpenAICompatibleProvider.shared_pool()
    b = OpenAICompatibleProvider.shared_pool()

    assert a is b
    await OpenAICompatibleProvider.close_shared_pool()
