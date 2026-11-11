"""Audit 9 pipeline/parsing findings: untrusted model output must not crash or inflate."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from reasoner.core.parsing import _parse_critique_scores, extract_json_any

pytestmark = pytest.mark.unit


def _fusion(reply):
    from reasoner.application.pipeline import ReasonerPipeline
    from reasoner.domain.pipeline_state import PipelineState

    p = object.__new__(ReasonerPipeline)
    p._call_llm_cached = AsyncMock(return_value=(reply, None))
    p._log = lambda *a, **k: None
    state = PipelineState(problem="Explain why the sky is blue in detail")
    asyncio.run(p._phase_fusion(state))
    return state.decomposition


def test_fusion_null_and_string_fields_are_coerced():
    d = _fusion('{"causal_chain": null, "assumptions": null, "failure_modes": null, "critical_sources": null}')
    assert d == {"causal_chain": [], "assumptions": [], "failure_modes": [], "critical_sources": []}
    d = _fusion('{"causal_chain": ["a string", {"step": 1}]}')
    assert d["causal_chain"] == [{"step": 1}]


def test_article_null_outline_does_not_raise():
    from reasoner.application.flows import article_phases
    from reasoner.domain.pipeline_state import PipelineState

    services = SimpleNamespace(call_llm=AsyncMock(return_value=('{"outline": null}', None)), log=lambda *a, **k: None)
    state = PipelineState(problem="x")
    asyncio.run(article_phases.run_article_outline_phase(state, services))
    assert state.writing_state["outline"] == []


def test_critique_scores_clamped_and_finite():
    out = _parse_critique_scores([{
        "perspective": "constructive", "logical_consistency": "inf", "evidence_support": 99,
        "failure_resilience": -5, "feasibility": "nan", "confidence_vs_accuracy_penalty": "inf",
    }])
    s = out[0]
    assert (s.logical_consistency, s.evidence_support, s.failure_resilience, s.feasibility) == (0.0, 10.0, 0.0, 0.0)
    assert s.confidence_vs_accuracy_penalty == 0.0


def test_article_verify_empty_metrics_is_not_perfect_support():
    from reasoner.application.flows import article_phases
    from reasoner.domain.pipeline_state import PipelineState

    for reply in ("", '{"gaps": ["g"]}', '{"metrics": null, "gaps": ["g"]}', '{"metrics": {"claim_support_ratio": null}, "gaps": ["g"]}'):
        services = SimpleNamespace(call_llm=AsyncMock(return_value=(reply, None)), log=lambda *a, **k: None)
        state = PipelineState(problem="x")
        asyncio.run(article_phases.run_article_adversarial_verify_phase(state, services))
        # An empty reply has no gaps to copy, but it must still take the low-support branch.
        assert state.writing_state["gaps_noted"] == (["g"] if reply else [])


def test_extract_json_any_array_with_trailing_prose():
    assert extract_json_any('[{"a":1},{"a":2}]\nHope this helps.') == [{"a": 1}, {"a": 2}]


def test_sandbox_malformed_reply_returns_failed_result():
    from reasoner.infrastructure.execution.container_sandbox import ContainerExecutionSandbox

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"stdout": ""}))
    sb = ContainerExecutionSandbox("http://w", "t", transport=transport)
    sb.health_check = AsyncMock(return_value=True)
    res = asyncio.run(sb.execute("print(1)"))
    assert res.success is False


def test_article_decomposition_is_a_dict():
    import inspect

    from reasoner.api.execution import pipeline

    assert 'state.decomposition = ["article workflow"]' not in inspect.getsource(pipeline)
