"""Integration smoke tests — one per reasoning method.

Tests that each preset builds a valid router and the pipeline
can be instantiated. A subset runs with real API calls.

Run: pytest tests/test_methods.py -v --run-integration
Skip API calls: pytest tests/test_methods.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from reasoner.application.services.preset_service import PresetService
from reasoner.core.settings import settings
from reasoner.domain.preset_registry import PRESETS as _PRESETS
from reasoner.presets import get_method_from_preset, is_valid_preset_name, resolve_preset_name

# ── Method-to-budget-preset mapping ──────────────────────────────────
METHOD_PRESETS: dict[str, str] = {
    "analogical":        "analogical-budget",
    "bayesian":          "bayesian-budget",
    "brainstorming":     "brainstorming-budget",
    "coding":            "coding-budget",
    "cove":              "cove-budget",
    "cross_language":    "cross-language-budget",
    "debate":            "debate-budget",
    "delphi":            "delphi-budget",
    "dialectical":       "dialectical-budget",
    "jury":              "jury-budget",
    "multi-perspective": "multi-perspective-budget",
    "pot":               "pot-budget",
    "pre_mortem":        "pre-mortem-budget",
    "research":          "research-budget",
    "scientific":        "scientific-budget",
    "self_discover":     "self-discover-budget",
    "socratic":          "socratic-budget",
    "sot":               "sot-budget",
    "tot":               "tot-budget",
    "writing":           "writing-budget",
}

# Methods to run with real API calls (subset for cost control)
FULL_RUN_METHODS = {
    "multi-perspective", "debate", "research", "writing",
    "jury", "socratic", "brainstorming", "pre_mortem",
}

def _is_usable_api_key(key: str | None) -> bool:
    """True only for a key that can actually reach the API.

    CI deliberately exports a non-empty placeholder OPENROUTER_API_KEY (see
    .github/workflows/test.yml) so provider/router construction succeeds
    offline for the mocked tests. A plain `bool(key)` check read that
    placeholder as a real credential, so the skipif below did not skip and
    the tests in this file went on to make live LLM calls, which failed with
    401 "Missing Authentication header" on every CI run. Treat known
    placeholder markers as "no key" so these live tests skip instead.
    """
    if not key:
        return False
    lowered = key.lower()
    markers = ("dummy", "placeholder", "not-for-production", "ci-test", "test-")
    return not any(marker in lowered for marker in markers)


_HAS_API_KEY = _is_usable_api_key(settings.OPENROUTER_API_KEY)


# ── Helper ───────────────────────────────────────────────────────────

def _build_router(preset_name: str):
    """Build a ProviderRouter for a given preset."""
    service = PresetService()
    effective, router = service.build_router(preset_name)
    return router, effective


# ── Preset validation tests (all methods, no API) ────────────────────

@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
def test_preset_exists_and_valid(method: str, preset_name: str) -> None:
    """Every method has a valid budget preset."""
    assert is_valid_preset_name(preset_name), f"Invalid preset: {preset_name}"
    resolved = resolve_preset_name(preset_name)
    assert resolved in _PRESETS, f"Preset {resolved} not in registry"


@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
def test_preset_builds_router(method: str, preset_name: str) -> None:
    """Every method preset builds a valid ProviderRouter."""
    router, effective = _build_router(preset_name)
    assert router is not None, f"Router is None for {preset_name}"
    assert effective, f"No effective preset for {preset_name}"


@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
def test_preset_has_method(method: str, preset_name: str) -> None:
    """get_method_from_preset returns the correct method."""
    actual_method = get_method_from_preset(preset_name)
    assert actual_method is not None, f"No method for {preset_name}"
    # Some methods map differently; just verify it returns something
    assert actual_method, f"Empty method for {preset_name}"


@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
def test_workflow_factory_has_strategy(method: str, preset_name: str) -> None:
    """Each method has a registered WorkflowStrategy."""
    from reasoner.application.flows.factory import WorkflowFactory
    from reasoner.domain.pipeline_state import PipelineState

    factory = WorkflowFactory()
    state = PipelineState(problem="test", method=method)
    strategy = factory.get_strategy(method)
    assert strategy is not None, f"No strategy for method: {method}"


@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
def test_strategy_has_phases(method: str, preset_name: str) -> None:
    """Each strategy returns a non-empty phase list."""
    from reasoner.application.flows.factory import WorkflowFactory
    from reasoner.domain.pipeline_state import PipelineState

    factory = WorkflowFactory()
    state = PipelineState(problem="test", method=method)
    strategy = factory.get_strategy(method)
    phases = strategy.get_phases(state)
    assert len(phases) > 0, f"No phases for method: {method}"


# ── Full pipeline smoke tests (API calls, subset only) ───────────────

# Drives real providers over the network. The skipif is not enough on its own:
# CI sets a dummy OPENROUTER_API_KEY so build_provider() succeeds, which makes
# _HAS_API_KEY true and lets these run against live endpoints. `integration`
# keeps them out of the default lane, where the marker is what CI filters on.
@pytest.mark.integration
@pytest.mark.skipif(not _HAS_API_KEY, reason="OPENROUTER_API_KEY not set")
@pytest.mark.parametrize("method,preset_name", [
    (m, p) for m, p in sorted(METHOD_PRESETS.items()) if m in FULL_RUN_METHODS
])
@pytest.mark.asyncio
async def test_full_pipeline_run(method: str, preset_name: str) -> None:
    """Run a full pipeline with real LLM calls for core methods."""
    from reasoner.pipeline import ReasonerPipeline

    router, effective = _build_router(preset_name)

    pipeline = ReasonerPipeline(
        router=router,
        top_k=2,
        parallel_perspectives=False,  # Sequential for cost control
        verbose=False,
        preset_name=effective,
        source_type="general",
    )

    problem = "What is 2 + 2? Answer in one sentence."

    try:
        state = await pipeline.run(problem)

        # Basic assertions
        assert state is not None, f"{method}: Pipeline returned None"
        assert state.problem, f"{method}: State has no problem"

        # Check that pipeline actually produced output
        if state.final_solution:
            solution = getattr(state.final_solution, "core_solution", "") or ""
            print(f"\n[{method}] Solution: {solution[:200]}")
            assert solution, f"{method}: Empty core_solution"
        elif state.candidates:
            print(f"\n[{method}] Candidates: {len(state.candidates)}")
            assert len(state.candidates) > 0, f"{method}: No candidates"

        print(f"[{method}] Tokens: {sum(t.get('total', 0) for t in state.phase_tokens.values())}")
        print(f"[{method}] Phases: {list(state.phase_durations.keys())}")
        print(f"[{method}] Errors: {state.errors}")

    except Exception as exc:
        pytest.fail(f"{method} pipeline failed: {exc}")


# ── All-methods light smoke (pipeline instantiation, no API) ─────────

@pytest.mark.parametrize("method,preset_name", sorted(METHOD_PRESETS.items()))
@pytest.mark.asyncio
async def test_pipeline_instantiation(method: str, preset_name: str) -> None:
    """Every method can instantiate a ReasonerPipeline."""
    from reasoner.pipeline import ReasonerPipeline

    router, effective = _build_router(preset_name)

    pipeline = ReasonerPipeline(
        router=router,
        top_k=2,
        parallel_perspectives=False,
        verbose=False,
        preset_name=effective,
        source_type="general",
    )
    assert pipeline is not None
    assert pipeline._get_method_from_preset() is not None


# ── Run marker ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    import pytest

    args = ["-v", "--tb=short"]
    if "--run-integration" in sys.argv:
        args.append("-m")
        args.append("not skip")
    else:
        args.append("-m")
        args.append("not integration")

    args.append(__file__)
    sys.exit(pytest.main(args))
