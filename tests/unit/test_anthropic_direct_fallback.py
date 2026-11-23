"""The direct Anthropic fallback works with the anthropic 2.x SDK.

A live run on 2026-11-19 (OpenRouter out of credits) showed every Anthropic
fallback failing with "AsyncMessages.create() got an unexpected keyword
argument 'temperature'": SDK 2.x targets API version 2026-10-21, which removed
sampling parameters. These tests check the call against the installed SDK's
real signature, so an SDK bump that changes it fails here, not in an outage.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from anthropic.resources.messages import AsyncMessages

from reasoner.infrastructure.llm.providers.direct import AnthropicDirectProvider


class _FakeClient:
    def __init__(self, content, **_kwargs):
        self.kwargs: dict = {}
        self.messages = SimpleNamespace(create=self._create)
        self._content = content

    async def _create(self, **kwargs):
        # Bind against the real SDK signature: an unknown keyword raises here
        # exactly as it does in the SDK.
        inspect.signature(AsyncMessages.create).bind(None, **kwargs)
        self.kwargs = kwargs
        return SimpleNamespace(content=self._content)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fake_client(monkeypatch):
    holder: dict = {}

    def install(content):
        def factory(**kwargs):
            holder["client"] = _FakeClient(content, **kwargs)
            return holder["client"]

        monkeypatch.setattr("anthropic.AsyncAnthropic", factory)
        return holder

    return install


@pytest.mark.asyncio
async def test_request_matches_the_installed_sdk_signature(fake_client):
    holder = fake_client([SimpleNamespace(type="text", text="ok")])

    out = await AnthropicDirectProvider(api_key="k").complete("sys", "hi", temperature=0.2)

    assert out == "ok"
    assert "temperature" not in holder["client"].kwargs


@pytest.mark.asyncio
async def test_answer_skips_a_leading_thinking_block(fake_client):
    fake_client([
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="part one, "),
        SimpleNamespace(type="text", text="part two"),
    ])

    out = await AnthropicDirectProvider(api_key="k").complete("sys", "hi")

    assert out == "part one, part two"
