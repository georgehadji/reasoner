"""Audit-6 regressions: cascade exhaustion raises, direct fallback skips client errors, image top-up."""
from unittest.mock import AsyncMock, patch

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm import executor as executor_mod
from reasoner.infrastructure.llm import router as router_mod
from reasoner.infrastructure.llm.base import LLMError
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.infrastructure.llm.image_generation import generate_images


class _FailRouter:
    def __init__(self, *a, **k):
        pass

    async def call(self, *a, **k):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_cascade_exhaustion_raises(monkeypatch):
    monkeypatch.setattr(executor_mod, "ProviderRouter", _FailRouter)
    monkeypatch.setattr(
        "reasoner.infrastructure.llm.registry.build_provider",
        lambda m: type("P", (), {"model": m})(),
    )
    ex = LLMExecutor(
        router=_FailRouter(), phase_configs={}, token_cache=None, caching_enabled=False,
        cascading_routing={"perspective": ["a", "b"]}, cascading_quality_check=False,
    )
    with pytest.raises(RuntimeError, match="All cascading models failed"):
        await ex.execute("perspective", "s", "u", PipelineState(problem="p"))


class _Vendor:
    model = "v"

    async def complete(self, **kw):
        return "ok" * 20


def _client_error():
    err = LLMError("bad request")
    err.status_code = 400
    return err


@pytest.mark.asyncio
@pytest.mark.parametrize("exc,expect_result", [(_client_error(), False), (RuntimeError("503"), True)])
async def test_direct_fallback_only_for_provider_faults(monkeypatch, exc, expect_result):
    from reasoner.core.settings import settings

    monkeypatch.setattr(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", True)
    monkeypatch.setattr(
        "reasoner.infrastructure.llm.providers.direct.build_fallback_provider", lambda n: _Vendor()
    )
    out = await router_mod._try_direct_fallback(
        "primary", "s", "u", exc, max_tokens=10, temperature=0.0
    )
    assert (out is not None) is expect_result


@pytest.mark.asyncio
async def test_image_retry_requests_only_missing_and_keeps_earlier():
    img = lambda n: {"image_data": f"data:image/png;base64,{n}", "model_used": "m"}  # noqa: E731
    with patch(
        "reasoner.infrastructure.llm.image_generation._run_generation_attempts",
        new_callable=AsyncMock,
    ) as attempts, patch(
        "reasoner.infrastructure.llm.image_generation._rewrite_prompt_for_policy_safety",
        new_callable=AsyncMock,
    ) as rewrite:
        attempts.side_effect = [([img("a")], ["flux: Request Moderated"]), ([img("b")], [])]
        rewrite.return_value = "safe rewrite of the prompt"
        result = await generate_images("p", preset="budget", enhance=False, num_images=2)

    assert result["success"] is True
    assert [i["image_data"][-1] for i in result["images"]] == ["a", "b"]
    assert attempts.await_args_list[1].kwargs["required_image_count"] == 1
