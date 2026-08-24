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
