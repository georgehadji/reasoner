"""Tests for ProviderRouter graceful degradation."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.llm.ports import DegradedLLMResponse


class FakeProvider:
    def __init__(self, model):
        self.model = model

    async def complete_with_retry(self, *args, **kwargs):
        raise asyncio.TimeoutError("always times out")


@pytest.mark.asyncio
async def test_all_providers_blocked_returns_degraded_response():
    """
    When both primary and fallback providers time out,
    router.call() should return a DegradedLLMResponse so the pipeline can continue.
    """
    primary = FakeProvider("primary-model")
    fallback = FakeProvider("fallback-model")

    router = ProviderRouter(
        primary=primary,
        fallback_table={"primary": fallback},
    )

    with patch(
        "reasoner.infrastructure.llm.router._call_with_circuit",
        side_effect=asyncio.TimeoutError("timed out"),
    ):
        result, _metadata = await router.call(
            role="primary",
            system_prompt="test",
            user_prompt="test",
        )

    assert isinstance(result, DegradedLLMResponse)
    assert result.degraded is True
    assert "both failed" in result.error or "no fallback" in result.error
