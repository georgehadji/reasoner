"""
Regression tests for synthesis integrity bugs: raw JSON leakage, stale citations,
malformed action blueprints, and scoring inversion.
Uses fakes — no API key required.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from reasoner.pipeline import ReasonerPipeline, TOKEN_OPTIMIZATION
from reasoner.models import PipelineState, CritiqueScore, PerspectiveType


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
        # ProviderRouter surface the perspective phase reads for its
        # lab-diversity check.
        self.primary = self._primary
        self.routing_table = {}
        self.fallback_table = {}

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
    await pipeline._phase_synthesis(state)

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
    await pipeline._phase_synthesis(state)

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
    await pipeline._phase_synthesis(state)

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

    await pipeline._phase_2_perspectives(state)

    assert len(state.candidates) == 1
    assert "Greek" not in state.candidates[0].content
    assert "Valid analysis of AGI timelines" in state.candidates[0].content
    assert calls.count("constructive") == 2


# ─────────────────────────────────────────────────────────────────────
# Milestone 6: Stress-test self-referential failures are filtered
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stress_test_filters_truncated_output():
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "constructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "scoring": json.dumps({"scores": []}),
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
