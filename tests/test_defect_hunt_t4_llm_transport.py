"""T4 defect hunt — LLM transport & routing.

Every fake in this module sits at a *transport* boundary:

  * ``httpx.MockTransport`` under a real ``openai.AsyncOpenAI`` for everything
    that goes through ``OpenAICompatibleProvider`` / ``OpenRouterProvider``.
    The provider, the router and the openai SDK's own request/response plumbing
    all run for real.
  * the vendor SDK *constructor* for the direct-fallback adapters in
    ``providers/direct.py``, which build their client internally and expose no
    injection point. The adapter under test is never itself mocked.

No test here makes a network call.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reasoner.infrastructure.llm.providers.openai_compat import (  # noqa: E402
    OpenAICompatibleProvider,
    OpenRouterProvider,
)
from reasoner.infrastructure.llm.router import ProviderRouter  # noqa: E402

pytestmark = pytest.mark.unit


# ─────────────────────────── transport helpers ────────────────────────────

def _completion(content: str = "ok", finish_reason: str = "stop", **usage):
    return {
        "id": "cmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": finish_reason,
        }],
        "usage": usage or None,
    }


def _attach(provider, handler):
    """Point *provider* at a real openai client over a mock httpx transport."""
    provider.client = openai.AsyncOpenAI(
        api_key="test-key",
        base_url="http://transport.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return provider


def _static(payload):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return handler


# ══════════════════ D1 — finish_reason lost on complete() ══════════════════

@pytest.mark.asyncio
async def test_complete_records_finish_reason_length():
    """A response cut off at max_tokens must be reported as such.

    ``finish_reason == "length"`` is the *only* signal that separates a
    truncated answer from a complete one once content has collapsed to a
    string (router._build_metadata, executor._retry_after_truncation).
    """
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-finish"),
        _static(_completion("PARTIAL {", finish_reason="length")),
    )

    await provider.complete("sys", "usr", max_tokens=16)

    assert provider.last_finish_reason == "length"


@pytest.mark.asyncio
async def test_complete_finish_reason_defaults_to_stop_when_absent():
    """Boundary: a provider that omits finish_reason must not report garbage."""
    payload = _completion("full answer")
    payload["choices"][0]["finish_reason"] = None
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-absent"),
        _static(payload),
    )

    await provider.complete("sys", "usr")

    assert provider.last_finish_reason == "stop"


@pytest.mark.asyncio
async def test_router_metadata_surfaces_truncation():
    """End-to-end: the executor's truncation retry keys off this metadata."""
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-router"),
        _static(_completion("PARTIAL {", finish_reason="length",
                            prompt_tokens=100, completion_tokens=16)),
    )
    router = ProviderRouter(primary=provider)

    _raw, metadata = await router.call("primary", "sys", "usr", max_tokens=16)

    assert metadata["finish_reason"] == "length"


# ═════════ D2 — bare OpenAICompatibleProvider reports no usage at all ═══════
# build_provider() returns a bare OpenAICompatibleProvider for the
# xAI-direct, DeepSeek-direct and Ollama lanes. Only OpenRouterProvider ever
# declared the last_* counters, and _record_usage is hasattr-guarded, so those
# lanes reported neither tokens nor cost — and executor's
# "estimate cost from token counts" fallback needs input_tokens > 0 to fire.

@pytest.mark.asyncio
async def test_direct_lane_provider_reports_token_usage():
    provider = _attach(
        OpenAICompatibleProvider(
            model="deepseek-v4-flash", api_key="k-direct-lane",
            base_url="https://api.deepseek.com/v1",
        ),
        _static(_completion("hi", prompt_tokens=1234, completion_tokens=56)),
    )

    await provider.complete("sys", "usr")

    assert provider.last_input_tokens == 1234
    assert provider.last_output_tokens == 56


@pytest.mark.asyncio
async def test_direct_lane_metadata_enables_cost_estimation():
    provider = _attach(
        OpenAICompatibleProvider(
            model="deepseek-v4-flash", api_key="k-direct-meta",
            base_url="https://api.deepseek.com/v1",
        ),
        _static(_completion("hi", prompt_tokens=1234, completion_tokens=56)),
    )
    router = ProviderRouter(primary=provider)

    _raw, metadata = await router.call("primary", "sys", "usr")

    # executor.execute(): `if cost_usd <= 0 and input_tokens > 0` — a missing
    # key defaults to 0 and silently bills the run at $0.
    assert metadata.get("input_tokens", 0) > 0
    assert "cost_usd" in metadata


@pytest.mark.asyncio
async def test_usage_counters_stay_zero_when_provider_omits_usage():
    """Boundary: no usage block must not raise and must not invent numbers."""
    provider = _attach(
        OpenAICompatibleProvider(model="qwen-max", api_key="k-nousage",
                                 base_url="http://transport.test/v1"),
        _static(_completion("hi")),
    )

    await provider.complete("sys", "usr")

    assert provider.last_input_tokens == 0
    assert provider.last_output_tokens == 0
    assert provider.last_cost_usd == 0.0


@pytest.mark.asyncio
async def test_openrouter_cost_reporting_still_works():
    """No-regression: OpenRouter's usage.cost must still reach metadata."""
    payload = _completion("hi", prompt_tokens=10, completion_tokens=20)
    payload["usage"]["cost"] = 0.0042
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-cost"),
        _static(payload),
    )
    router = ProviderRouter(primary=provider)

    _raw, metadata = await router.call("primary", "sys", "usr")

    assert metadata["cost_usd"] == pytest.approx(0.0042)
    assert metadata["input_tokens"] == 10
    assert metadata["output_tokens"] == 20


# ═══════════ D3 — stream_complete never awaits the SDK coroutine ═══════════
# `openai.resources.chat.completions.AsyncCompletions.create` is an
# `async def`; `async with <coroutine>` is a TypeError. The pre-existing test
# for this method stubs `create` as a *sync* function returning an async
# context manager, which is not the SDK's shape, so the missing await was
# invisible.

def _sse_stream(*chunks: dict):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )
    return handler


def _chunk(content: str | None = None, finish_reason: str | None = None):
    delta = {"content": content} if content is not None else {}
    return {
        "id": "chunk", "object": "chat.completion.chunk", "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


@pytest.mark.asyncio
async def test_stream_complete_works_against_the_real_sdk():
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-stream"),
        _sse_stream(_chunk("Hel"), _chunk("lo"), _chunk(finish_reason="length")),
    )

    chunks = [c async for c in provider.stream_complete("sys", "usr")]

    assert "".join(chunks) == "Hello"
    assert provider.last_finish_reason == "length"


@pytest.mark.asyncio
async def test_stream_complete_tolerates_empty_stream():
    """Boundary: a stream that yields no content chunk must simply end."""
    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="k-stream-empty"),
        _sse_stream(_chunk(finish_reason="stop")),
    )

    assert [c async for c in provider.stream_complete("sys", "usr")] == []


# ══════ D4 — direct-fallback adapters leak their transport on every call ═══
# _try_direct_fallback builds a fresh provider per call; each of the three
# SDK-backed adapters constructs a client and never closes it.

class _RecordingClient:
    """Stands in for a vendor SDK client; records construction and closure."""

    instances: list["_RecordingClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.call_kwargs: dict = {}
        _RecordingClient.instances.append(self)

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        await self.close()
        return False

    # -- anthropic shape --
    @property
    def messages(self):
        async def create(**kwargs):
            self.call_kwargs = kwargs
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text="anthropic-ok")]
            )
        return types.SimpleNamespace(create=create)

    # -- openai shape --
    @property
    def chat(self):
        async def create(**kwargs):
            self.call_kwargs = kwargs
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="openai-ok"))])
        return types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create))

    # -- google shape --
    @property
    def models(self):
        async def generate_content(**kwargs):
            self.call_kwargs = kwargs
            return types.SimpleNamespace(text="google-ok")
        return types.SimpleNamespace(generate_content=generate_content)


@pytest.fixture
def recording_sdk(monkeypatch):
    """Swap all three vendor SDK constructors for a recorder."""
    _RecordingClient.instances = []

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _RecordingClient)
    monkeypatch.setattr(openai, "AsyncOpenAI", _RecordingClient)

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _RecordingGoogleClient, raising=False)
    return _RecordingClient


class _RecordingGoogleClient(_RecordingClient):
    """google-genai exposes its async surface as ``Client(...).aio``."""

    @property
    def aio(self):
        return types.SimpleNamespace(models=_RecordingClient.models.fget(self))


@pytest.mark.parametrize("provider_name", ["anthropic", "openai"])
@pytest.mark.asyncio
async def test_direct_fallback_adapter_closes_its_client(recording_sdk, provider_name):
    """The SDK-backed adapters build a client per call; it must be released."""
    from reasoner.infrastructure.llm.providers import direct

    cls = {
        "anthropic": direct.AnthropicDirectProvider,
        "openai": direct.OpenAIDirectProvider,
    }[provider_name]

    text = await cls(api_key="k").complete("sys", "usr")

    assert text  # the adapter still works
    assert len(recording_sdk.instances) == 1
    assert recording_sdk.instances[0].closed is True, (
        f"{cls.__name__} leaked its transport client"
    )


@pytest.mark.asyncio
async def test_google_direct_uses_the_real_genai_async_surface(recording_sdk):
    """`genai.aio` does not exist — the lane raised AttributeError on every call.

    google-genai owns no closable transport, so this asserts the *API shape*
    rather than closure: Client(...).aio.models.generate_content(...).
    """
    from reasoner.infrastructure.llm.providers import direct

    text = await direct.GoogleDirectProvider(api_key="k").complete("sys", "usr")

    assert text == "google-ok"


@pytest.mark.asyncio
async def test_direct_fallback_adapter_closes_client_on_error(recording_sdk):
    """Boundary: the error path must release the transport too."""
    from reasoner.infrastructure.llm.base import LLMError
    from reasoner.infrastructure.llm.providers import direct

    class _Boom(_RecordingClient):
        @property
        def messages(self):
            async def create(**_kwargs):
                raise RuntimeError("upstream 500")
            return types.SimpleNamespace(create=create)

    import anthropic
    anthropic.AsyncAnthropic = _Boom  # undone by the fixture's monkeypatch

    with pytest.raises(LLMError):
        await direct.AnthropicDirectProvider(api_key="k").complete("sys", "usr")

    assert _RecordingClient.instances[0].closed is True


# ═══ D5 — OpenAIDirectProvider sends parameters its own default model rejects ═
# OpenAICompatibleProvider already encodes both facts in this repo:
# `_uses_completion_tokens()` (gpt-/o-series need max_completion_tokens) and
# `_FIXED_TEMPERATURE_MARKERS` (gpt-5* rejects a custom temperature).
# The direct adapter, whose default model is gpt-5.5, honours neither.

@pytest.mark.asyncio
async def test_openai_direct_respects_the_repo_parameter_rules(recording_sdk):
    from reasoner.infrastructure.llm.providers import direct

    provider = direct.OpenAIDirectProvider(api_key="k")  # default model gpt-5.5
    probe = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    probe.model = provider.model
    assert probe._uses_completion_tokens() is True
    assert probe._supports_temperature() is False

    await provider.complete("sys", "usr", max_tokens=256, temperature=0.2)

    sent = recording_sdk.instances[0].call_kwargs
    assert "max_tokens" not in sent
    assert sent["max_completion_tokens"] == 256
    assert "temperature" not in sent


@pytest.mark.asyncio
async def test_openai_direct_still_sends_max_tokens_for_legacy_models(recording_sdk):
    """No-regression: a non-gpt-5 model keeps the classic parameter names."""
    from reasoner.infrastructure.llm.providers import direct

    provider = direct.OpenAIDirectProvider(api_key="k", model="mistral-large-latest")
    await provider.complete("sys", "usr", max_tokens=256, temperature=0.2)

    sent = recording_sdk.instances[0].call_kwargs
    assert sent["max_tokens"] == 256
    assert sent["temperature"] == 0.2


# ═════════ D6 — per-call metadata races on a process-shared provider ════════
# ProviderRouter._dedupe hands every router the same provider instance for a
# given (class, model, credential) tuple. The per-call counters live on that
# instance and are read by _build_metadata *after* the concurrency semaphore
# has been released, so a concurrent call to the same model can overwrite them
# in between. Reported as STATISTICAL — this is a race, not a certainty.

@pytest.mark.xfail(
    strict=True,
    reason=(
        "CONFIRMED, unfixed: ProviderRouter._build_metadata reads the provider's "
        "per-call counters after _call_with_circuit has released the concurrency "
        "semaphore, and _dedupe shares one provider instance process-wide. "
        "Fixing it changes _call_with_circuit's return type — cross-boundary, "
        "see docs/reports/defect-hunt-2026-09-01/T4-llm-transport.md D7."
    ),
)
@pytest.mark.asyncio
async def test_concurrent_calls_do_not_crosswire_usage_metadata():
    trials = 120

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        marker = body["max_tokens"]
        return httpx.Response(200, json=_completion(
            str(marker), prompt_tokens=marker, completion_tokens=1,
        ))

    provider = _attach(
        OpenRouterProvider(model="anthropic/claude-sonnet-5", api_key="race-key"),
        handler,
    )
    router = ProviderRouter(primary=provider)

    async def one(marker: int) -> bool:
        raw, metadata = await router.call(
            "primary", "sys", "usr", max_tokens=marker,
        )
        return int(raw) == metadata.get("input_tokens")

    results = await asyncio.gather(*(one(100 + i) for i in range(trials)))
    mismatches = results.count(False)
    assert mismatches == 0, (
        f"{mismatches}/{trials} calls received another call's usage counters"
    )
