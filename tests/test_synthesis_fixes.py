"""
Regression tests for synthesis integrity bugs: raw JSON leakage, stale citations,
malformed action blueprints, and scoring inversion.
Uses fakes — no API key required.
"""

import json

import pytest

from reasoner.application.flows.perspective_phases import run_perspectives_phase
from reasoner.application.flows.services import PipelineWorkflowServices
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.models import CritiqueScore, PerspectiveType, PipelineState
from reasoner.pipeline import TOKEN_OPTIMIZATION, ReasonerPipeline


def _svc(pipeline):
    """The WorkflowServices a phase function takes, bound to this pipeline."""
    return PipelineWorkflowServices(pipeline)


@pytest.fixture(autouse=True)
def disable_token_cache():
    original = TOKEN_OPTIMIZATION["caching"]
    TOKEN_OPTIMIZATION["caching"] = False
    yield
    TOKEN_OPTIMIZATION["caching"] = original


class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []
        self._primary = FakeProvider()
        self.primary = self._primary
        self.routing_table: dict[str, FakeProvider] = {}

    def get(self, role: str):
        return self._primary

    async def call(self, role: str, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return self.responses.get(role, "{}"), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


# ─────────────────────────────────────────────────────────────────────
# Milestone 1: Raw JSON must not leak into core_solution
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesis_reconstructs_prose_when_solution_tag_missing():
    raw_response = """
```json
{
  "critical_insights": ["Insight A", "Insight B"],
  "action_blueprint": [{"step": "1", "action": "Do X"}],
  "open_questions": ["Q1"],
  "sources": []
}
```
"""
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "synthesis": raw_response,
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Test")
    # Bypass earlier phases
    state.task_type = "analytical"
    state.decomposition = {"causal_chain": [], "assumptions": [], "failure_modes": []}
    await run_synthesis_phase(state, _svc(pipeline))

    assert state.final_solution is not None
    cs = state.final_solution.core_solution
    assert "```json" not in cs
    assert "Insight A" in cs
    assert "Do X" in cs


# ─────────────────────────────────────────────────────────────────────
# Milestone 2: Citation validator warns on hallucinated URLs
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesis_logs_warning_for_foreign_citation():
    raw_response = """
[SOLUTION]
We should act now because evidence shows X [Bad Source](https://example.com/not-in-context).
[/SOLUTION]
```json
{"critical_insights": [], "sources": []}
```
"""
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "synthesis": raw_response,
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Test")
    state.task_type = "analytical"
    state.decomposition = {"causal_chain": [], "assumptions": [], "failure_modes": []}
    state.vetted_context = [{"url": "https://allowed.com", "summary": "ok"}]
    await run_synthesis_phase(state, _svc(pipeline))

    assert any(
        "Citation integrity warning" in entry and "example.com/not-in-context" in entry
        for entry in state.phase_logs
    )


# ─────────────────────────────────────────────────────────────────────
# Milestone 3: Malformed action blueprint is sanitized
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_action_blueprint_does_not_produce_question_marks():
    raw_response = """
[SOLUTION]
Test solution.
[/SOLUTION]
```json
{
  "action_blueprint": [{"?": ""}, {"step": "", "action": ""}, {"step": "2", "action": "Act"}]
}
```
"""
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "synthesis": raw_response,
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Test")
    state.task_type = "analytical"
    state.decomposition = {"causal_chain": [], "assumptions": [], "failure_modes": []}
    await run_synthesis_phase(state, _svc(pipeline))

    bp = state.final_solution.action_blueprint
    assert len(bp) == 1
    assert bp[0].get("step") == "2"
    assert bp[0].get("action") == "Act"


# ─────────────────────────────────────────────────────────────────────
# Milestone 7: confidence_vs_accuracy_penalty affects total score
# ─────────────────────────────────────────────────────────────────────

def test_critique_score_total_includes_penalty():
    high_confidence_wrong = CritiqueScore(
        perspective=PerspectiveType.CONSTRUCTIVE,
        logical_consistency=8.0,
        evidence_support=8.0,
        failure_resilience=8.0,
        feasibility=8.0,
        bias_flags=[],
        steel_man="",
        confidence_vs_accuracy_penalty=3.0,
    )
    humble = CritiqueScore(
        perspective=PerspectiveType.DESTRUCTIVE,
        logical_consistency=8.0,
        evidence_support=8.0,
        failure_resilience=8.0,
        feasibility=8.0,
        bias_flags=[],
        steel_man="",
        confidence_vs_accuracy_penalty=0.0,
    )
    assert high_confidence_wrong.total == 5.0
    assert humble.total == 8.0
    assert humble.total > high_confidence_wrong.total


# ─────────────────────────────────────────────────────────────────────
# Milestone 5: Perspective hallucination filter
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_perspective_filter_regenerates_hallucinated_greek_text():
    calls = []

    class CountingRouter(FakeRouter):
        async def call(self, role, system_prompt, user_prompt, **kwargs):
            calls.append(role)
            if len(calls) == 1:
                # First call returns hallucinated content
                return json.dumps({"core_analysis": "The Greek text hints at nuances.", "key_insights": []}), {"model": "fake", "input_tokens": 10, "output_tokens": 10}
            return json.dumps({"core_analysis": "Valid analysis of AGI timelines.", "key_insights": []}), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    router = CountingRouter({})
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="When will AGI arrive?")
    state.language = "English"
    pipeline.perspectives = ["constructive"]

    await run_perspectives_phase(state, _svc(pipeline), perspectives=pipeline.perspectives)

    assert len(state.candidates) == 1
    assert "Greek" not in state.candidates[0].content
    assert "Valid analysis of AGI timelines" in state.candidates[0].content
    assert calls.count("constructive") == 2


@pytest.mark.asyncio
async def test_configured_perspectives_reach_phase_without_explicit_kwarg():
    """pipeline.perspectives must reach Phase 2 through production wiring.

    Regression: run_perspectives_phase() fell back to DEFAULT_PERSPECTIVES
    whenever its `perspectives` kwarg was omitted — exactly what happens on the
    real WorkflowRunner path (application/flows/runner.py calls
    `self.services.run_phase(step, state)` with no kwargs; only the hand-rolled
    /api/run-with-context endpoint passed `perspectives=pipeline.perspectives`
    explicitly). Narrowing pipeline.perspectives therefore had no effect on any
    normal run. PipelineWorkflowServices.perspectives now surfaces it and the
    phase's getattr-tolerant default picks it up.
    """
    calls = []

    class CountingRouter(FakeRouter):
        async def call(self, role, system_prompt, user_prompt, **kwargs):
            calls.append(role)
            return json.dumps({"core_analysis": f"{role} analysis", "key_insights": []}), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    router = CountingRouter({})
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    pipeline.perspectives = ["constructive", "destructive"]

    # No `perspectives=` kwarg — exactly what the production WorkflowRunner path does.
    await run_perspectives_phase(state, _svc(pipeline))

    assert set(calls) == {"constructive", "destructive"}
    assert len(state.candidates) == 2


def _recording_router(calls):
    class RecordingRouter(FakeRouter):
        async def call(self, role, system_prompt, user_prompt, **kwargs):
            calls.append(role)
            return json.dumps({"core_analysis": f"{role} analysis", "key_insights": []}), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    return RecordingRouter({})


@pytest.mark.asyncio
async def test_empty_pipeline_perspectives_fall_back_to_defaults():
    calls = []
    pipeline = ReasonerPipeline(router=_recording_router(calls), preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    pipeline.perspectives = []

    await run_perspectives_phase(state, _svc(pipeline))

    assert set(calls) == {"constructive", "destructive", "systemic", "minimalist"}


@pytest.mark.asyncio
async def test_duplicate_perspectives_run_once():
    calls = []
    pipeline = ReasonerPipeline(router=_recording_router(calls), preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    pipeline.perspectives = ["constructive", "constructive", "destructive"]

    await run_perspectives_phase(state, _svc(pipeline))

    assert sorted(calls) == ["constructive", "destructive"]
    assert len(state.candidates) == 2


@pytest.mark.asyncio
async def test_diversity_warning_is_computed_over_active_perspectives_only():
    """Two active roles on one model must warn even if the inactive roles differ."""
    from types import SimpleNamespace

    calls = []
    router = _recording_router(calls)
    router.routing_table = {
        "constructive": SimpleNamespace(model="anthropic/a"),
        "destructive": SimpleNamespace(model="anthropic/a"),
        "systemic": SimpleNamespace(model="deepseek/b"),
        "minimalist": SimpleNamespace(model="mistralai/c"),
    }
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    pipeline.perspectives = ["constructive", "destructive"]

    await run_perspectives_phase(state, _svc(pipeline))

    warnings = [e for e in state.pending_events if e.get("type") == "phase_warning"]
    assert any("diversity collapsed" in w["message"] for w in warnings)


# ─────────────────────────────────────────────────────────────────────
# Milestone 6: Stress-test self-referential failures are filtered
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stress_test_filters_truncated_output():
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "constructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "scoring": json.dumps({"scores": [
            # Non-empty because the per-phase quality gate now runs on this path
            # and fails "Critique & Pruning" on an empty scores list. The test is
            # about stress-test filtering, so the critique only has to be well-formed enough for the
            # run to reach it.
            {"perspective": "constructive", "logical_consistency": 8.0,
             "evidence_support": 7.5, "failure_resilience": 7.0,
             "feasibility": 8.5, "bias_flags": [], "steel_man": "strongest form"},
        ]}),
        "stress_testing": json.dumps({
            "stress_tests": [
                {"scenario": "constraint_violation", "survival_rate": 0.7, "failure_mode": "truncated output due to length limits"},
                {"scenario": "adversarial", "survival_rate": 0.5, "failure_mode": "supply chain disruption"},
            ]
        }),
        "synthesis": json.dumps({"core_solution": "done"}),
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = await pipeline.run("test problem")

    failure_modes = [st.failure_mode for st in state.stress_results]
    assert "truncated output due to length limits" not in failure_modes
    assert "supply chain disruption" in failure_modes
