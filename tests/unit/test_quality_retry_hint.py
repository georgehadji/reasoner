"""A quality-gate retry must be a different call from the attempt that failed.

Before: runner.run_phase stored the judge's suggestions in state.quality_hints
and nothing read them, so the retry sent the identical prompt -- and with
TOKEN_CACHING on (the default) the executor served the cached answer that had
just failed, for free, changing nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from reasoner.application.flows.base import PhaseStep
from reasoner.application.flows.runner import WorkflowRunner
from reasoner.application.flows.services import PipelineWorkflowServices
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.quality.criteria import PhaseQualityResult


def _services():
    calls: list[dict] = []

    async def _call_llm_cached(**kwargs):
        calls.append(kwargs)
        return "{}", {"model": "fake"}

    pipeline = SimpleNamespace(router=None, _call_llm_cached=_call_llm_cached, _log=lambda *a: None)
    return PipelineWorkflowServices(pipeline), calls


@pytest.mark.asyncio
async def test_retry_carries_the_hint_and_skips_the_cache(monkeypatch):
    services, calls = _services()
    runner = WorkflowRunner(services)
    verdicts = iter([
        PhaseQualityResult(passed=False, score=2.0, reason="thin", suggestions=["cite a source"]),
        PhaseQualityResult(passed=True, score=8.0, reason="ok"),
    ])

    async def _evaluate(name, state, attempt=1):
        return next(verdicts)

    monkeypatch.setattr(runner.monitor, "evaluate", _evaluate)
    monkeypatch.setattr("reasoner.application.flows.runner.reset_phase_state", lambda n, s: None)

    async def _phase(state, svc, **kwargs):
        await svc.call_llm(role="constructive", system_prompt="S", user_prompt="BASE", state=state)

    state = PipelineState(problem="q")
    assert await runner.run_phase(PhaseStep(2, "Perspectives", _phase, lambda s: {}), state)

    first, retry = calls
    assert first["user_prompt"] == "BASE" and "bypass_cache_read" not in first
    assert retry["bypass_cache_read"] is True
    assert "<<<EXTERNAL_CONTENT>>>\ncite a source\n<<<END_EXTERNAL_CONTENT>>>" in retry["user_prompt"]
    assert retry["user_prompt"].endswith("\n\nBASE")
    assert "cite a source" not in retry["system_prompt"]  # never the instruction channel
    assert state.quality_hints == {}  # popped when the phase ended


@pytest.mark.asyncio
async def test_a_hint_for_another_phase_is_ignored():
    services, calls = _services()
    state = PipelineState(problem="q")
    state._current_phase_key = "Phase 3: Critique & Pruning"
    state.quality_hints["Perspectives"] = "stale"

    await services.call_llm(role="scoring", system_prompt="S", user_prompt="BASE", state=state)

    assert calls[0]["user_prompt"] == "BASE" and "bypass_cache_read" not in calls[0]


class _DictCache:
    def __init__(self):
        self.store: dict[tuple, str] = {}

    async def get(self, problem, phase, model_id, prompt):
        return self.store.get((problem, phase, model_id, prompt))

    async def set(self, problem, phase, model_id, prompt, response, tokens_used):
        self.store[(problem, phase, model_id, prompt)] = response


class _Router:
    def __init__(self):
        self.kwargs: list[dict] = []

    def get(self, role):
        return SimpleNamespace(model="m")

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.kwargs.append(kwargs)
        return f"answer {len(self.kwargs)}", {"model": "m", "input_tokens": 1, "output_tokens": 1}


@pytest.mark.asyncio
async def test_executor_bypass_skips_the_lookup_but_stores_the_new_answer():
    router = _Router()
    executor = LLMExecutor(router=router, phase_configs={}, token_cache=_DictCache(), caching_enabled=True)
    state = PipelineState(problem="q")
    call = dict(role="constructive", system_prompt="S", user_prompt="P", state=state)

    assert (await executor.execute(**call))[0] == "answer 1"
    assert (await executor.execute(**call))[0] == "answer 1"  # cache hit: no router call
    assert len(router.kwargs) == 1

    assert (await executor.execute(**call, bypass_cache_read=True))[0] == "answer 2"
    assert "bypass_cache_read" not in router.kwargs[-1]  # never forwarded to the provider
    assert (await executor.execute(**call))[0] == "answer 2"  # the fresh answer replaced it
