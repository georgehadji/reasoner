"""
Architecture Integration: Real-API method-by-method pipeline tests.

Runs every reasoning method through a complete pipeline with live
OpenRouter API calls and validates completion, synthesis quality,
and method-specific state invariants.

Usage:
  python -m pytest tests/test_arch_integration_methods.py -v --run-slow
"""

from __future__ import annotations

import os
import pytest
import asyncio

from reasoner.pipeline import ReasonerPipeline
from reasoner.application.services.preset_service import PresetService
from reasoner.domain.preset_core import get_method_from_preset

pytestmark = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    ),
]

# ── Problem prompts tailored to each method ──────────────────────────

_PROBLEMS: dict[str, str] = {
    "multi_perspective": "What are the three most impactful ways cities can reduce carbon emissions, considering cost, feasibility, and public acceptance?",
    "debate": "Should remote work be the default for knowledge workers? Present the strongest arguments for and against.",
    "jury": "A startup has $2M funding and must choose between investing in sales or product development. What would an expert panel recommend?",
    "research": "What are the leading theories explaining the Fermi paradox?",
    "scientific": "Design an experiment to test whether a coin is fair. Include hypothesis, methodology, and expected outcomes.",
    "socratic": "What is justice? Use Socratic questioning to explore this concept.",
    "pre_mortem": "A company is about to launch a new social media platform. Conduct a pre-mortem: imagine it failed and explain why.",
    "bayesian": "You believe it will rain tomorrow with 30% confidence. You check the weather forecast which is 80% accurate. Update your belief.",
    "dialectical": "Freedom vs security: present a thesis-antithesis-synthesis analysis.",
    "analogical": "Compare the structure of an atom to the structure of a solar system. What are the limits of this analogy?",
    "delphi": "A panel of experts must estimate the year AI will surpass human intelligence. Run a Delphi consensus process.",
    "cove": "Fact-check the claim: 'Coffee consumption reduces the risk of heart disease by 50%.' Use chain-of-verification.",
    "sot": "Explain quantum computing to a high school student using skeleton-of-thought: first outline, then fill in details.",
    "tot": "You need to optimize delivery routes for 5 trucks serving 20 cities. Use tree-of-thought to explore different branching strategies.",
    "pot": "Calculate the probability of drawing at least one ace when drawing 5 cards from a standard deck. Show your work using code.",
    "self_discover": "Solve this puzzle: If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets? Explain how you arrived at your answer.",
    "writing": "Write a short informative article about the history and health benefits of meditation.",
    "coding": "Write a Python function that finds the longest palindromic substring in a given string. Include tests.",
    "brainstorming": "Generate 10 creative business ideas for reducing plastic waste in oceans. Be specific and innovative.",
    "cross_language": "¿Cuáles son las ventajas y desventajas de la energía nuclear comparada con la energía solar?",
}

# ── Method → Preset mapping ──────────────────────────────────────────

_METHOD_PRESETS: list[tuple[str, str]] = [
    ("multi_perspective", "multi-perspective-budget"),
    ("debate", "debate-budget"),
    ("jury", "jury-budget"),
    ("research", "research-budget"),
    ("scientific", "scientific-budget"),
    ("socratic", "socratic-budget"),
    ("pre_mortem", "pre-mortem-budget"),
    ("bayesian", "bayesian-budget"),
    ("dialectical", "dialectical-budget"),
    ("analogical", "analogical-budget"),
    ("delphi", "delphi-budget"),
    ("cove", "cove-budget"),
    ("sot", "sot-budget"),
    ("tot", "tot-budget"),
    ("pot", "pot-budget"),
    ("self_discover", "self-discover-budget"),
    ("writing", "writing-budget"),
    ("coding", "coding-budget"),
    ("brainstorming", "brainstorming-budget"),
    ("cross_language", "cross-language-budget"),
]


def _build_router(preset_id: str):
    """Build a ProviderRouter for a preset using PresetService."""
    svc = PresetService()
    _, router = svc.build_router(preset_id)
    return router


class TestAllMethodsComplete:
    """Every method should run to completion with a valid synthesis."""

    @pytest.mark.parametrize("method, preset_id", _METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_method_produces_synthesis(self, method, preset_id):
        problem = _PROBLEMS.get(method, "What is 2+2? Explain your reasoning.")
        router = _build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(problem)

        # ── Basic completion invariants ──
        assert state.task_type is not None, f"{method}: task_type not set"
        assert state.final_solution is not None, f"{method}: no final_solution"
        assert state.final_solution.core_solution, f"{method}: core_solution empty"
        assert len(state.final_solution.core_solution) > 20, (
            f"{method}: core_solution too short ({len(state.final_solution.core_solution)} chars)"
        )

        # ── No fatal errors ──
        fatal = [e for e in state.errors if "Pipeline processing error" in e]
        assert not fatal, f"{method}: fatal errors: {fatal}"
        non_fatal = [e for e in state.errors if e not in fatal]
        if non_fatal:
            pytest.fail(f"{method}: non-fatal errors present: {non_fatal[:3]}")


class TestAllMethodsTracksTokens:
    """Every method should produce non-zero token counts."""

    @pytest.mark.parametrize("method, preset_id", _METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_method_tracks_tokens(self, method, preset_id):
        problem = _PROBLEMS.get(method, "What is 2+2? Explain your reasoning.")
        router = _build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(problem)

        total = sum(t.get("total", 0) for t in state.detailed_token_usage.values())
        assert total > 0, f"{method}: expected non-zero token usage"
        assert state.detailed_token_usage, f"{method}: no token tracking data"


class TestAllMethodsStateInvariants:
    """Each method should populate its method-specific state fields."""

    @pytest.mark.parametrize("method, preset_id", [
        ("debate", "debate-budget"),
        ("jury", "jury-budget"),
        ("pre_mortem", "pre-mortem-budget"),
        ("bayesian", "bayesian-budget"),
        ("dialectical", "dialectical-budget"),
        ("analogical", "analogical-budget"),
        ("delphi", "delphi-budget"),
    ])
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_method_state_populated(self, method, preset_id):
        problem = _PROBLEMS.get(method, "Explain your reasoning process.")
        router = _build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(problem)

        if method == "debate":
            assert state.debate_rounds is not None, f"{method}: debate_rounds not set"
        elif method == "jury":
            assert state.generation_candidates is not None, f"{method}: no generation candidates"
        elif method == "pre_mortem":
            assert state.pre_mortem_state is not None, f"{method}: pre_mortem_state not set"
            assert isinstance(state.pre_mortem_state, dict), f"{method}: pre_mortem_state not dict"
        elif method == "bayesian":
            assert state.bayesian_state is not None, f"{method}: bayesian_state not set"
            assert isinstance(state.bayesian_state, dict), f"{method}: bayesian_state not dict"
        elif method == "dialectical":
            assert state.dialectical_state is not None, f"{method}: dialectical_state not set"
            assert isinstance(state.dialectical_state, dict), f"{method}: dialectical_state not dict"
        elif method == "analogical":
            assert state.analogical_state is not None, f"{method}: analogical_state not set"
            assert isinstance(state.analogical_state, dict), f"{method}: analogical_state not dict"
        elif method == "delphi":
            assert state.delphi_state is not None, f"{method}: delphi_state not set"
            assert isinstance(state.delphi_state, dict), f"{method}: delphi_state not dict"


class TestAllMethodsDecomposition:
    """Every method should complete decomposition with assumptions."""

    @pytest.mark.parametrize("method, preset_id", _METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_method_has_decomposition(self, method, preset_id):
        problem = _PROBLEMS.get(method, "Explain your reasoning process.")
        router = _build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(problem)

        assert state.decomposition is not None, f"{method}: decomposition not set"
        assert state.task_type is not None, f"{method}: no task type classified"


class TestAllMethodsEpistemicLabeling:
    """Every method should label claims in the final solution."""

    @pytest.mark.parametrize("method, preset_id", _METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_method_labels_claims(self, method, preset_id):
        problem = _PROBLEMS.get(method, "Explain your reasoning process.")
        router = _build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(problem)

        assert state.final_solution is not None, f"{method}: no final_solution"
        assert state.final_solution.meta_audit is not None, f"{method}: no meta_audit"
        # meta_audit should have at least a dominant_bias or remaining_uncertainty
        has_audit = (
            state.final_solution.meta_audit.dominant_bias
            or state.final_solution.meta_audit.remaining_uncertainty
        )
        assert has_audit, f"{method}: meta_audit fields are empty"
