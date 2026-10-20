"""Every billed call reaches the run's cost (BIL-2).

Three paths skipped cost accounting:
(a) cascade calls added tokens but no cost, and rejected attempts added nothing;
(b) the direct-vendor fallback returned no usage, so it priced at $0;
(c) DIRECT/WEB_SEARCH ``done`` frames carried no ``total_cost_usd``, which is
    what metering bills.
See docs/plans/audit-remediation-2026-10-20.md, BIL-2.
"""

from __future__ import annotations

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm import executor as executor_mod
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.infrastructure.llm.pricing_resolver import call_cost_usd


class _Router:
    """A ProviderRouter stand-in: every call bills $0.01 and answers by model."""

    answers: dict[str, str] = {}

    def __init__(self, primary=None, **kwargs):
        self.model = getattr(primary, "model", "m")

    def get(self, role):
        return self

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        meta = {"model": self.model, "cost_usd": 0.01, "input_tokens": 100, "output_tokens": 10}
        return self.answers.get(self.model, "fine answer"), meta


@pytest.mark.asyncio
async def test_rejected_and_accepted_cascade_attempts_are_both_billed(monkeypatch):
    _Router.answers = {"bad-model": "   ", "good-model": "fine answer"}  # first is empty
    monkeypatch.setattr(executor_mod, "ProviderRouter", _Router)
    monkeypatch.setattr(
        "reasoner.infrastructure.llm.registry.build_provider",
        lambda model_id: type("P", (), {"model": model_id})(),
    )
    ex = LLMExecutor(
        router=_Router(), phase_configs={}, token_cache=None, caching_enabled=False,
        cascading_routing={"perspective": ["bad-model", "good-model"]},
        cascading_quality_check=False,
    )
    state = PipelineState(problem="p")

    raw, _ = await ex.execute("perspective", "sys", "usr", state)

    assert raw == "fine answer"
    assert state.total_cost_usd == pytest.approx(0.02), "both attempts were paid for"


def test_reported_cost_wins():
    assert call_cost_usd({"model": "x", "cost_usd": 0.5, "input_tokens": 10}) == 0.5


def test_missing_cost_is_estimated_from_tokens():
    cost = call_cost_usd({"model": "anthropic/claude-sonnet-5", "input_tokens": 1_000_000,
                          "output_tokens": 0})
    assert cost > 0


def test_no_tokens_no_cost():
    assert call_cost_usd({"model": "x"}) == 0.0


@pytest.mark.asyncio
async def test_direct_vendor_fallback_reports_estimated_usage(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.infrastructure.llm import router as router_mod

    class _Vendor:
        model = "claude-direct"

        async def complete(self, **kw):
            return "x" * 400

    monkeypatch.setattr(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", True)
    monkeypatch.setattr(
        "reasoner.infrastructure.llm.providers.direct.build_fallback_provider",
        lambda name: _Vendor(),
    )
    out = await router_mod._try_direct_fallback(
        "primary", "s" * 40, "u" * 360, RuntimeError("402"), max_tokens=10, temperature=0.0,
    )
    assert out is not None
    _, meta = out
    assert meta["input_tokens"] == 100 and meta["output_tokens"] == 100
    assert meta["usage_estimated"] is True


@pytest.mark.asyncio
async def test_direct_answer_done_frame_carries_cost(monkeypatch):
    import json

    from reasoner.api.execution import direct
    from reasoner.application.services.run_metering import extract_run_cost

    async def fake_call(*a, **k):
        return "answer", {"model": "x", "cost_usd": 0.003, "input_tokens": 50, "output_tokens": 5}

    monkeypatch.setattr(direct, "_call_with_model_fallback", fake_call)
    frames = [f async for f in direct._stream_direct_answer(router=None, problem="q", run_id="r")]
    done = [f for f in frames if '"type": "done"' in f or '"type":"done"' in f]
    assert done, frames
    assert extract_run_cost(done[-1]) == pytest.approx(0.003)
    assert json.loads(done[-1][len("data: "):])["total_cost_usd"] == pytest.approx(0.003)



@pytest.mark.asyncio
async def test_normal_call_without_reported_cost_is_estimated_and_billed():
    """The non-cascade path: tokens but no cost_usd still bill the run."""

    class _NoCostRouter(_Router):
        async def call(self, role, system_prompt, user_prompt, **kwargs):
            return "fine answer", {"model": "anthropic/claude-sonnet-5",
                                   "input_tokens": 1000, "output_tokens": 100}

    ex = LLMExecutor(router=_NoCostRouter(), phase_configs={}, token_cache=None,
                     caching_enabled=False)
    state = PipelineState(problem="p")
    raw, _ = await ex.execute("perspective", "sys", "usr", state)
    assert raw == "fine answer"
    assert state.total_cost_usd > 0
