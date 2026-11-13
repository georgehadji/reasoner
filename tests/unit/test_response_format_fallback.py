"""Parameter-filter 404 retries without response_format (live run 43444508034)."""

from __future__ import annotations

import types

import httpx
import openai
import pytest

from reasoner.infrastructure.llm.providers import openai_compat
from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider

_STRICT_SYSTEM = "Output ONLY valid JSON. No prose."
_STRICT_USER = 'Output JSON: {"task_type": "..."}'


def _not_found(text: str) -> openai.NotFoundError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return openai.NotFoundError(text, response=httpx.Response(404, request=request), body=None)


def _provider(errors: list[Exception], calls: list[dict]) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(model="meta-llama/llama-4-scout", api_key="sk-test")

    async def create(**kwargs):
        calls.append(kwargs)
        if errors:
            raise errors.pop(0)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"task_type": "x"}'),
                finish_reason="stop",
            )],
            usage=None,
        )

    provider.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    return provider


@pytest.fixture(autouse=True)
def _json_mode_on(monkeypatch):
    monkeypatch.setattr(
        openai_compat, "_json_response_format", lambda *a: {"type": "json_object"}
    )


@pytest.mark.asyncio
async def test_parameter_filter_404_retries_without_response_format():
    calls: list[dict] = []
    provider = _provider(
        [_not_found(
            "No endpoints found for meta-llama/llama-4-scout. Every candidate endpoint "
            "was removed during routing: Filter by Parameters removed deepinfra/fp8"
        )],
        calls,
    )
    text = await provider.complete(_STRICT_SYSTEM, _STRICT_USER)
    assert "task_type" in text
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


@pytest.mark.asyncio
async def test_unrelated_404_is_not_retried():
    calls: list[dict] = []
    provider = _provider([_not_found("No endpoints found for meta-llama/llama-4-scout.")], calls)
    with pytest.raises(Exception, match="No endpoints found"):
        await provider.complete(_STRICT_SYSTEM, _STRICT_USER)
    assert len(calls) == 1
