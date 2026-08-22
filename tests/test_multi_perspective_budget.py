"""
Tests for the multi-perspective-budget preset.

Covers:
- Preset configuration: routing roles, lab diversity, flags
- Router construction: all roles resolve, describe() is valid
- Full mock pipeline run: all 6 phases complete, state populated correctly
- Role call tracking: correct router roles called per phase
"""

from __future__ import annotations

import json
import pytest

# Import core.search before ReasonerPipeline to resolve a circular import
# between infrastructure/search/discovery.py and core/search.py.
import reasoner.core.search  # noqa: F401

from reasoner.presets import get_preset
from reasoner.pipeline import ReasonerPipeline
from reasoner.application.pipeline import TOKEN_OPTIMIZATION
from reasoner.models import PipelineState

PRESET_ID = "multi-perspective-budget"

# ── Canned LLM responses keyed by router role ─────────────────────────

_PERSPECTIVE_RESPONSE = json.dumps({
    "core_analysis": "A well-reasoned analysis of the problem.",
    "key_insights": ["Insight A", "Insight B"],
    "confidence": 7,
})

_SCORING_RESPONSE = json.dumps({
    "scores": [
        {
            "perspective": "constructive",
            "logical_consistency": 8,
            "evidence_support": 7,
            "failure_resilience": 7,
            "feasibility": 8,
            "total": 30,
            "bias_flags": [],
            "steel_man": "Strong point about X.",
        },
        {
            "perspective": "destructive",
            "logical_consistency": 7,
            "evidence_support": 6,
            "failure_resilience": 8,
            "feasibility": 7,
            "total": 28,
            "bias_flags": [],
            "steel_man": "Counter-point about Y.",
        },
    ]
})

_STRESS_RESPONSE = json.dumps({
    "stress_tests": [
        {
            "scenario": "optimal",
            "survival_rate": 0.9,
            "failure_mode": "none",
            "recovery_path": "proceed as planned",
        }
    ]
})

_SYNTHESIS_RESPONSE = json.dumps({
    "core_solution": "Based on all perspectives, the recommended approach is X.",
    "action_blueprint": ["Step 1: Do A", "Step 2: Do B"],
    "confidence_level": "HIGH",
    "epistemic_label": "VERIFIED",
})

FAKE_RESPONSES: dict[str, str] = {
    "prompt_enhancement": json.dumps({"enhanced_problem": "Refined problem statement."}),
    "classification": json.dumps({"task_type": "analytical", "domain": "general"}),
    "decomposition": json.dumps({
        "causal_chain": ["Factor A leads to B"],
        "assumptions": ["Assumption 1"],
        "failure_modes": ["Risk 1"],
    }),
    "constructive": _PERSPECTIVE_RESPONSE,
    "destructive": _PERSPECTIVE_RESPONSE,
    "systemic": _PERSPECTIVE_RESPONSE,
    "minimalist": _PERSPECTIVE_RESPONSE,
    "scoring": _SCORING_RESPONSE,
    "stress_testing": _STRESS_RESPONSE,
    "synthesis": _SYNTHESIS_RESPONSE,
}


class FakeProvider:
    def __init__(self, model: str = "fake-model"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class TrackingFakeRouter:
    """Fake router that records every call and returns canned responses."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []
        self._primary = FakeProvider()
        self.primary = self._primary
        self.routing_table = {}

    def get(self, role: str):
        return self._primary

    async def call(self, role: str, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        response = self.responses.get(role, "{}")
        return response, {"model": "fake", "input_tokens": 10, "output_tokens": 20}

    def describe(self):
        return {"[primary]": "fake-model"}

    def called_roles(self) -> list[str]:
        return [role for role, _, _ in self.calls]


# ── 1. Preset configuration ───────────────────────────────────────────

class TestPresetConfig:
    @pytest.fixture
    def preset(self):
        return get_preset(PRESET_ID)

    def test_preset_loads(self, preset):
        assert preset is not None
        assert preset.primary_id

    def test_required_routing_roles_present(self, preset):
        # Classification + decomposition were merged into a single "fusion"
        # role (application/pipeline.py::_phase_fusion) — no longer separate
        # routing entries.
        required = {
            "fusion",
            "constructive", "destructive", "systemic", "minimalist",
            "scoring", "stress_testing", "synthesis",
        }
        assert required.issubset(set(preset.routing))

    def test_top_k_is_at_least_two(self, preset):
        assert preset.top_k >= 2

    def test_parallel_perspectives_enabled(self, preset):
        assert preset.parallel_perspectives is True

    @pytest.mark.xfail(
        reason="Known gap: multi-perspective-budget has no per-role fallback_routing "
        "(CLAUDE.md's 'fail to cross-lab equivalent' principle) — only 2/48 presets "
        "define it. See REMEDIATION_PLAN.md unclassified-triage section.",
        strict=True,
    )
    def test_fallback_routing_configured(self, preset):
        assert preset.fallback_routing, "Budget preset should define fallback routing"
        assert "constructive" in preset.fallback_routing

    def test_required_tier_is_free(self, preset):
        from reasoner.domain.saas import SubscriptionTier
        assert preset.required_tier == SubscriptionTier.FREE

    def test_cross_lab_diversity_phase_2(self, preset):
        """Phase 2 perspective roles must use models from at least 3 different labs."""
        from reasoner.infrastructure.llm.registry import _REGISTRY

        phase_2_roles = ["constructive", "destructive", "systemic", "minimalist"]
        model_ids = [preset.routing[r] for r in phase_2_roles if r in preset.routing]

        labs: set[str] = set()
        for logical_id in model_ids:
            entry = _REGISTRY.get(logical_id, {})
            api_model: str = entry.get("model", "")
            # Extract lab prefix from "lab/model-name" format
            lab = api_model.split("/")[0] if "/" in api_model else api_model
            if lab:
                labs.add(lab)

        assert len(labs) >= 3, (
            f"Phase 2 needs ≥3 labs for diversity, got {len(labs)}: {labs}. "
            f"Model IDs: {dict(zip(phase_2_roles, model_ids, strict=False))}"
        )

    def test_scorer_is_independent_lab(self, preset):
        """Scorer must come from a different lab than the primary Phase 2 model."""
        from reasoner.infrastructure.llm.registry import _REGISTRY

        def lab_of(logical_id: str) -> str:
            entry = _REGISTRY.get(logical_id, {})
            api_model = entry.get("model", "")
            return api_model.split("/")[0] if "/" in api_model else ""

        constructive_lab = lab_of(preset.routing.get("constructive", ""))
        scorer_lab = lab_of(preset.routing.get("scoring", ""))
        assert constructive_lab != scorer_lab, (
            f"Scorer ({scorer_lab}) must not be the same lab as constructive ({constructive_lab})"
        )


# ── 2. Router construction ────────────────────────────────────────────

class TestRouterBuilding:
    @pytest.fixture
    def router(self):
        from reasoner.application.services.preset_service import PresetService
        _, r = PresetService().build_router(PRESET_ID)
        return r

    def test_router_builds_without_error(self, router):
        assert router is not None

    def test_describe_returns_primary(self, router):
        desc = router.describe()
        assert "[primary]" in desc
        assert desc["[primary]"]

    def test_all_routing_roles_resolve(self):
        from reasoner.application.services.preset_service import PresetService
        preset = get_preset(PRESET_ID)
        _, router = PresetService().build_router(PRESET_ID)
        for role in preset.routing:
            provider = router.get(role)
            assert provider is not None, f"Role '{role}' did not resolve to a provider"

    def test_primary_provider_has_model(self, router):
        primary = router.get("primary")
        assert hasattr(primary, "model") and primary.model


# ── 3. Full mock pipeline run ─────────────────────────────────────────

class TestMockPipelineRun:

    @pytest.fixture
    def router(self):
        return TrackingFakeRouter(FAKE_RESPONSES)

    @pytest.fixture
    def pipeline(self, router):
        return ReasonerPipeline(
            router=router,
            preset_name=PRESET_ID,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
        )

    @pytest.mark.asyncio
    async def test_run_completes_and_returns_state(self, pipeline):
        state = await pipeline.run("What is the best way to learn a new programming language?")
        assert isinstance(state, PipelineState)

    @pytest.mark.asyncio
    async def test_problem_preserved_in_state(self, pipeline):
        problem = "Should companies adopt a four-day work week?"
        state = await pipeline.run(problem)
        assert state.problem == problem

    @pytest.mark.asyncio
    async def test_preset_name_preserved_in_state(self, pipeline):
        state = await pipeline.run("test problem")
        assert state.preset_name == PRESET_ID

    @pytest.mark.asyncio
    async def test_task_type_classified(self, pipeline):
        state = await pipeline.run("test problem")
        assert state.task_type is not None

    @pytest.mark.asyncio
    async def test_perspectives_generated(self, pipeline):
        # Generated perspectives land in state.candidates (perspective_phases.py),
        # not state.perspectives — that attribute doesn't exist on PipelineState.
        state = await pipeline.run("test problem")
        assert len(state.candidates) > 0

    @pytest.mark.asyncio
    async def test_final_solution_produced(self, pipeline):
        state = await pipeline.run("test problem")
        assert state.final_solution is not None
        assert state.final_solution.core_solution
        assert len(state.final_solution.core_solution) > 5

    @pytest.mark.asyncio
    async def test_no_critical_pipeline_errors(self, pipeline):
        state = await pipeline.run("test problem")
        critical = [e for e in state.errors if "Pipeline processing error" in e]
        assert not critical, f"Unexpected critical errors: {critical}"

    @pytest.mark.asyncio
    async def test_token_usage_tracked(self, pipeline):
        state = await pipeline.run("test problem")
        assert state.detailed_token_usage, "Token usage should be non-empty"
        total = sum(t.get("total", 0) for t in state.detailed_token_usage.values())
        assert total >= 0


# ── 4. Role call tracking ─────────────────────────────────────────────

class TestPhaseRoleCalls:
    """Verify the correct router roles are invoked for each phase."""

    @pytest.fixture
    async def state_and_router(self, monkeypatch):
        # These tests assert which roles the router was called for -- the
        # process-wide token-response cache (application/pipeline.py's
        # module-level `token_cache`) can serve a cached response and skip
        # the router call entirely for an identical (problem, phase, model,
        # prompt) tuple, which is exactly what every test in this class
        # would produce since they all drive the same problem string through
        # TrackingFakeRouter's single fake model. Caching is a real
        # optimization in production; it's fundamentally at odds with
        # "was the router called" as a test assertion, so it's disabled for
        # just this pipeline instance rather than relying on the global
        # reset_token_cache() autouse fixture to always win a race against
        # Phase 2's concurrent perspective calls.
        monkeypatch.setitem(TOKEN_OPTIMIZATION, "caching", False)
        router = TrackingFakeRouter(FAKE_RESPONSES)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=PRESET_ID,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
        )
        state = await pipeline.run("What are the trade-offs between SQL and NoSQL databases?")
        return state, router

    @pytest.mark.asyncio
    async def test_fusion_role_called(self, state_and_router):
        # Classification + decomposition were merged into a single "fusion"
        # role (application/pipeline.py::_phase_fusion).
        _, router = state_and_router
        assert "fusion" in router.called_roles()

    @pytest.mark.asyncio
    async def test_phase_2_perspective_roles_called(self, state_and_router):
        _, router = state_and_router
        called = router.called_roles()
        assert "constructive" in called
        assert "destructive" in called
        assert "systemic" in called
        assert "minimalist" in called

    @pytest.mark.asyncio
    async def test_scoring_role_called(self, state_and_router):
        _, router = state_and_router
        assert "scoring" in router.called_roles()

    @pytest.mark.asyncio
    async def test_synthesis_role_called(self, state_and_router):
        _, router = state_and_router
        assert "synthesis" in router.called_roles()

    @pytest.mark.asyncio
    async def test_fusion_called_before_perspectives(self, state_and_router):
        _, router = state_and_router
        roles = router.called_roles()
        fusion_idx = next((i for i, r in enumerate(roles) if r == "fusion"), -1)
        constructive_idx = next((i for i, r in enumerate(roles) if r == "constructive"), -1)
        assert fusion_idx < constructive_idx, (
            "fusion (classification+decomposition) must be called before perspectives"
        )

    @pytest.mark.asyncio
    async def test_synthesis_called_after_scoring(self, state_and_router):
        _, router = state_and_router
        roles = router.called_roles()
        scoring_idx = next((i for i, r in enumerate(roles) if r == "scoring"), -1)
        synthesis_idx = next((i for i, r in enumerate(roles) if r == "synthesis"), -1)
        assert scoring_idx < synthesis_idx, (
            "scoring must complete before synthesis"
        )
