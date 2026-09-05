"""Tests for ProviderRouter graceful degradation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reasoner.infrastructure.llm.ports import DegradedLLMResponse
from reasoner.infrastructure.llm.router import ProviderRouter


class FakeProvider:
    def __init__(self, model):
        self.model = model

    async def complete_with_retry(self, *args, **kwargs):
        raise TimeoutError("always times out")


@pytest.mark.asyncio
async def test_all_providers_blocked_returns_degraded_response():
    """
    When both primary and fallback providers time out,
    router.call() should return a DegradedLLMResponse so the pipeline can continue.

    MULTI_PROVIDER_FALLBACK_ENABLED defaults true (de76b6d, OpenRouter SPOF
    fallback), so router.call() also tries direct-SDK providers (anthropic,
    openai, google, mistral, ...) after the primary/fallback_table path is
    exhausted. Without disabling it, this test made a real network call to
    whichever direct provider had a key configured in the environment
    (observed: Mistral answered "It looks like you're testing!..." for real)
    instead of exercising the degraded-response path. Disable it here so the
    test is isolated and deterministic.
    """
    from reasoner.core.settings import settings

    primary = FakeProvider("primary-model")
    fallback = FakeProvider("fallback-model")

    router = ProviderRouter(
        primary=primary,
        fallback_table={"primary": fallback},
    )

    with patch.object(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", False):
        with patch(
            "reasoner.infrastructure.llm.router._call_with_circuit",
            side_effect=TimeoutError("timed out"),
        ):
            result, _metadata = await router.call(
                role="primary",
                system_prompt="test",
                user_prompt="test",
            )

    assert isinstance(result, DegradedLLMResponse)
    assert result.degraded is True
    assert "both failed" in result.error or "no fallback" in result.error


class TestProviderApiErrorsReachTheFallbackChain:
    """A provider HTTP error must be recoverable, not fatal to the phase.

    ProviderRouter._execute_call recovers from exactly ``TimeoutError`` and
    ``LLMError``. ``providers/openai_compat.py`` used to re-raise the raw
    OpenAI SDK exception, so every provider HTTP error walked straight past the
    fallback chain into the phase. Observed live: OpenRouter routed
    ``nousresearch/hermes-4-70b`` to Nebius, which answered
    ``404 ... The model NousResearch/Hermes-4-70B does not exist``; the
    destructive perspective was dropped with no fallback attempted, quietly
    reducing cross-lab diversity from four generators to three while the run
    still reported success.
    """

    @staticmethod
    def _api_error(cls, status: int):
        import httpx
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(status, request=request)
        return cls("provider returned error", response=response, body=None)

    def test_sdk_errors_convert_to_the_type_the_router_catches(self):
        """The conversion the router's recovery depends on."""
        import openai

        from reasoner.infrastructure.llm.base import LLMError
        from reasoner.infrastructure.llm.providers.openai_compat import _as_llm_error

        converted = _as_llm_error(
            "nousresearch/hermes-4-70b",
            self._api_error(openai.NotFoundError, 404),
        )
        assert isinstance(converted, LLMError)
        assert "hermes-4-70b" in str(converted)
        assert "404" in str(converted)

    def test_sdk_timeout_is_covered_too(self):
        """openai.APITimeoutError is not a builtin TimeoutError.

        It descends from APIConnectionError, so the router's ``except
        TimeoutError`` branch never saw an SDK timeout either.
        """
        import httpx
        import openai

        from reasoner.infrastructure.llm.base import LLMError
        from reasoner.infrastructure.llm.providers.openai_compat import _as_llm_error

        assert not issubclass(openai.APITimeoutError, TimeoutError), (
            "if the SDK ever makes this a builtin TimeoutError, the router's "
            "timeout branch handles it and this translation can be narrowed"
        )
        exc = openai.APITimeoutError(
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        )
        assert isinstance(_as_llm_error("some/model", exc), LLMError)

    @pytest.mark.asyncio
    async def test_a_404_on_the_primary_falls_back_instead_of_raising(self):
        """End of the chain: a 404 must produce a fallback call, not an exception."""
        import openai

        from reasoner.core.settings import settings
        from reasoner.infrastructure.llm.providers.openai_compat import _as_llm_error

        primary = FakeProvider("nousresearch/hermes-4-70b")
        fallback = FakeProvider("anthropic/claude-sonnet-5")
        router = ProviderRouter(primary=primary, fallback_table={"primary": fallback})

        attempted: list[str] = []

        async def _circuit(provider, *args, **kwargs):
            attempted.append(provider.model)
            if provider is primary:
                raise _as_llm_error(
                    provider.model, self._api_error(openai.NotFoundError, 404)
                )
            return "fallback answered"

        with patch.object(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", False):
            with patch(
                "reasoner.infrastructure.llm.router._call_with_circuit",
                side_effect=_circuit,
            ):
                result, metadata = await router.call(
                    role="primary", system_prompt="test", user_prompt="test",
                )

        assert attempted == ["nousresearch/hermes-4-70b", "anthropic/claude-sonnet-5"], (
            f"fallback was not attempted after the 404; attempts={attempted}"
        )
        assert result == "fallback answered"
        assert metadata.get("model") == "anthropic/claude-sonnet-5"

    @pytest.mark.asyncio
    async def test_complete_translates_a_provider_404(self):
        """The regression guard proper: the SDK error must not escape complete().

        The tests above construct the LLMError themselves, so they would pass
        even with the translation removed. This one drives a real
        OpenAICompatibleProvider whose client raises the SDK exception, which
        is the path that was broken.
        """
        import openai

        from reasoner.infrastructure.llm.base import LLMError
        from reasoner.infrastructure.llm.providers.openai_compat import (
            OpenAICompatibleProvider,
        )

        provider = OpenAICompatibleProvider(
            model="nousresearch/hermes-4-70b", api_key="test-key",
        )

        async def _raise_404(**kwargs):
            raise self._api_error(openai.NotFoundError, 404)

        with patch.object(
            provider.client.chat.completions, "create", side_effect=_raise_404
        ):
            with pytest.raises(LLMError) as caught:
                await provider.complete("sys", "user", max_tokens=64)

        assert "hermes-4-70b" in str(caught.value)
        assert not isinstance(caught.value, openai.APIError), (
            "the SDK exception must be translated, not merely re-raised"
        )
