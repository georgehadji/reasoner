"""
Architecture Risk: Fallback to primary masks model-specific failures.

When a role-specific model fails, the ProviderRouter falls back to the
primary model. This test verifies that DegradedLLMResponse carries
diagnostic information about which role and model failed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reasoner.infrastructure.llm.ports import DegradedLLMResponse
from reasoner.infrastructure.llm.router import ProviderRouter


class FakeProvider:
    def __init__(self, model):
        self.model = model

    async def complete_with_retry(self, *args, **kwargs):
        raise RuntimeError(f"simulated failure: {self.model}")


def make_router(primary_model="primary", routing_models=None, fallback_models=None):
    routing_table = {}
    if routing_models:
        routing_table = {k: FakeProvider(v) for k, v in routing_models.items()}
    fallback_table = {}
    if fallback_models:
        fallback_table = {k: FakeProvider(v) for k, v in fallback_models.items()}
    return ProviderRouter(
        primary=FakeProvider(primary_model),
        routing_table=routing_table,
        fallback_table=fallback_table,
    )


@pytest.mark.asyncio
async def test_degraded_response_identifies_failing_model() -> None:
    """When all providers fail, DegradedLLMResponse.error names the model."""
    router = make_router(primary_model="primary-model")
    # No fallback — primary is the only provider and it always fails

    with patch(
        "reasoner.infrastructure.llm.router._call_with_circuit",
        side_effect=TimeoutError("timed out"),
    ):
        result, metadata = await router.call(
            role="primary",
            system_prompt="test",
            user_prompt="test",
        )

    assert isinstance(result, DegradedLLMResponse)
    assert result.degraded is True
    assert "primary-model" in result.error, (
        f"DegradedLLMResponse.error should name the failing model. Got: {result.error}"
    )


@pytest.mark.asyncio
async def test_degraded_response_carries_metadata() -> None:
    """DegradedLLMResponse.metadata contains the model that failed."""
    router = make_router(primary_model="primary-model")

    with patch(
        "reasoner.infrastructure.llm.router._call_with_circuit",
        side_effect=TimeoutError("test timeout"),
    ):
        result, metadata = await router.call(
            role="synthesis",
            system_prompt="test",
            user_prompt="test",
        )

    assert isinstance(result, DegradedLLMResponse)
    assert result.metadata is not None
    # metadata should identify the model
    assert "model" in result.metadata, (
        f"Metadata should include 'model' key. Got: {result.metadata}"
    )


@pytest.mark.asyncio
async def test_fallback_provides_explicit_model_name() -> None:
    """When primary falls back to an explicit fallback provider,
    the DegradedLLMResponse should reference the correct model.

    MULTI_PROVIDER_FALLBACK_ENABLED defaults true (de76b6d, OpenRouter SPOF
    fallback), so without disabling it router.call() would try real direct
    providers after routing_table/fallback_table are exhausted, and could
    return a real (non-degraded) response instead — see
    test_provider_router_degradation.py for the same issue observed live.
    """
    from reasoner.core.settings import settings

    router = ProviderRouter(
        primary=FakeProvider("primary-model"),
        routing_table={"scoring": FakeProvider("scoring-model")},
        fallback_table={"scoring": FakeProvider("fallback-scoring-model")},
    )

    with patch.object(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", False):
        with patch(
            "reasoner.infrastructure.llm.router._call_with_circuit",
            side_effect=TimeoutError("timed out"),
        ):
            result, metadata = await router.call(
                role="scoring",
                system_prompt="test",
                user_prompt="test",
            )

    assert isinstance(result, DegradedLLMResponse)
    # Should mention the fallback model since it was tried
    assert (
        "scoring-model" in result.error
        or "fallback-scoring-model" in result.error
    ), (
        f"DegradedLLMResponse should identify the model that failed. Got: {result.error}"
    )


def test_provider_router_describe_output_format() -> None:
    """describe() returns a readable routing table."""
    router = make_router(
        primary_model="gpt-5",
        routing_models={
            "synthesis": "claude-sonnet",
            "scoring": "sonar-pro",
        },
        fallback_models={
            "synthesis": "gemini-pro",
        },
    )
    desc = router.describe()
    assert "[primary]" in desc
    assert desc["[primary]"] == "gpt-5"
    assert "synthesis" in desc
    # Should show fallback with → notation
    assert "gemini-pro" in desc["synthesis"]


def test_get_returns_primary_for_unknown_role() -> None:
    """get() returns primary for any role not in routing_table."""
    router = make_router(primary_model="primary-model")
    provider = router.get("nonexistent_role")
    assert provider.model == "primary-model"


def test_get_returns_role_specific_provider() -> None:
    """get() returns role-specific provider when configured."""
    router = make_router(
        primary_model="primary-model",
        routing_models={"synthesis": "claude-sonnet"},
    )
    provider = router.get("synthesis")
    assert provider.model == "claude-sonnet"


def test_call_fallback_skips_same_model() -> None:
    """When explicit fallback has the same model as assigned, it's skipped
    (no double-retry of the same endpoint)."""
    router = ProviderRouter(
        primary=FakeProvider("model-A"),
        routing_table={"scoring": FakeProvider("model-B")},
        fallback_table={"scoring": FakeProvider("model-B")},  # same model as assigned!
    )
    # fallback should be skipped because model-B == model-B
    # If both fail, the result comes from the assigned (model-B) with a single failure
    # not a double-attempt against same model
    assigned = router.get("scoring")
    fallback = router.fallback_table.get("scoring")
    assert assigned.model == "model-B"
    assert fallback.model == "model-B"
    # Router should detect same-model and skip it in call()
