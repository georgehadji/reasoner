"""Regression tests for safe array indexing in neuro providers.

Verifies that providers return empty string/list instead of crashing
with IndexError when the API returns a 200 with empty choices/data arrays.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock


class FakeResponse:
    """Minimal httpx.Response mock."""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _make_provider(cls, **overrides):
    from reasoner.neuro.providers import ProviderConfig

    defaults = {
        "provider": "openai",
        "model": "test-model",
        "api_key": "test-key",
        "api_base": "http://localhost:9999",
    }
    defaults.update(overrides)
    cfg = ProviderConfig(**defaults)
    return cls(cfg)


def _run(coro):
    return asyncio.run(coro)


# ── Reproducer: empty choices/data → no crash ────────────────


def test_openai_reasoning_empty_choices():
    """Fails without fix: IndexError on empty choices array."""
    from reasoner.neuro.providers import OpenAIReasoning

    provider = _make_provider(OpenAIReasoning)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse({"choices": []}))
    )
    assert _run(provider.generate("test prompt")) == ""


def test_openai_embedding_empty_data():
    """Fails without fix: IndexError on empty data array."""
    from reasoner.neuro.providers import OpenAIEmbedding

    provider = _make_provider(OpenAIEmbedding)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse({"data": []}))
    )
    assert _run(provider.embed("test text")) == []


def test_openrouter_reasoning_empty_choices():
    from reasoner.neuro.providers import OpenRouterReasoning

    provider = _make_provider(OpenRouterReasoning, provider="openrouter")
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse({"choices": []}))
    )
    assert _run(provider.generate("test prompt")) == ""


def test_huggingface_embedding_empty_response():
    from reasoner.neuro.providers import HuggingFaceEmbedding

    provider = _make_provider(HuggingFaceEmbedding, provider="huggingface")
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse([]))
    )
    assert _run(provider.embed("test text")) == []


# ── Boundary: non-empty responses still work ─────────────────


def test_openai_reasoning_normal_response():
    """Regression: normal non-empty response still returns content."""
    from reasoner.neuro.providers import OpenAIReasoning

    provider = _make_provider(OpenAIReasoning)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(
            return_value=FakeResponse(
                {"choices": [{"message": {"content": "hello world"}}]}
            )
        )
    )
    assert _run(provider.generate("test prompt")) == "hello world"


def test_openai_embedding_normal_response():
    """Regression: normal embedding response returns vector."""
    from reasoner.neuro.providers import OpenAIEmbedding

    provider = _make_provider(OpenAIEmbedding)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(
            return_value=FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        )
    )
    assert _run(provider.embed("test text")) == [0.1, 0.2, 0.3]


# ── Boundary: missing key entirely ───────────────────────────


def test_openai_reasoning_missing_choices_key():
    """Boundary: response has no 'choices' key at all."""
    from reasoner.neuro.providers import OpenAIReasoning

    provider = _make_provider(OpenAIReasoning)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse({"error": "rate limited"}))
    )
    assert _run(provider.generate("test prompt")) == ""


def test_openai_embedding_missing_data_key():
    """Boundary: response has no 'data' key at all."""
    from reasoner.neuro.providers import OpenAIEmbedding

    provider = _make_provider(OpenAIEmbedding)
    provider._get_client = lambda: MagicMock(
        post=AsyncMock(return_value=FakeResponse({"error": "rate limited"}))
    )
    assert _run(provider.embed("test text")) == []
