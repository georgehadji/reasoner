"""
Deterministic end-to-end tests for ALL budget presets.

Unlike ``test_e2e_budget_presets.py`` (which requires a funded OPENROUTER_API_KEY
and is marked slow/integration), this module exercises the **real pipeline
orchestration for every budget preset** with a deterministic mock LLM. It is
designed to surface code-path bugs:

  - presets whose routing roles don't match what the phases call
  - unmigrated / mis-named methods (factory dispatch failures)
  - attribute errors, missing phase methods, broken parsing
  - synthesis paths that fail to produce a ``final_solution``

The mock replaces ``ProviderRouter.call`` so no network is used and no credits
are spent, but the full ``ReasonerPipeline.run`` path (fusion → method strategy
→ synthesis → verification) executes exactly as in production.

Run with: python -m pytest tests/test_e2e_budget_presets_mock.py -v
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from reasoner.application.services.preset_service import PresetService
from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import PRESETS

# Every budget preset in the registry (25 as of v3.4), sorted for stable output.
ALL_BUDGET_PRESETS = sorted(p for p in PRESETS if p.endswith("-budget"))

_SIMPLE_PROBLEM = "What is the capital of France and why is it historically significant?"

# Shared preset service — the same router-construction path used by
# PipelineOrchestrator.preflight in production.
_PRESET_SERVICE = PresetService()

# Roles whose callers expect structured JSON output (and then fall back to
# defaults on parse failure). We give them a generous JSON payload so every
# parser key resolves to a sensible value.
_JSON_ROLES = {
    "fusion", "classification", "decomposition", "synthesis", "stress_testing",
    "verifier", "meta_evaluator", "scoring", "context_vetting",
}

# A rich JSON payload whose keys are a superset of what any phase parser looks
# for. Crucially it includes a long ``core_solution`` so the synthesis phase
# always produces a non-empty FinalSolution even when other keys are ignored.
_RICH_JSON = {
    "task_type": "factual",
    "language": "English",
    "sub_questions": [
        {"question": "What is the capital of France?", "why": "Identify the city."},
        {"question": "Why is it historically significant?", "why": "Establish context."},
    ],
    "core_solution": (
        "Paris is the capital of France. It has been the political, economic, "
        "and cultural heart of the country for over a thousand years, serving as "
        "the seat of French kings, the epicenter of the French Revolution, and "
        "a global hub for art, philosophy, and governance."
    ),
    "critical_insights": [
        "Paris became the capital under the Capetian dynasty.",
        "The French Revolution cemented Paris as a center of political power.",
    ],
    "action_blueprint": [
        {"step": "1", "action": "Establish Paris as the capital.", "time_horizon": "immediate",
         "go_criteria": "confirmed", "fallback": "re-check"},
    ],
    "open_questions": ["How did Paris's role evolve during the 20th century?"],
    "claim_labels": {"Paris is the capital": "verified"},
    "meta_audit": {
        "most_dangerous_assumption": "That political and cultural significance overlap.",
        "dominant_bias": "Eurocentric framing",
        "remaining_uncertainty": "low",
        "assumption_failure_impact": "limited",
        "non_obvious_insight": "Paris's centrality shaped French unification.",
    },
    "sources": [{"title": "Encyclopedia", "url": "https://example.org/paris"}],
    "layout_hints": {},
    "evidence": {},
    # Method-specific parser keys (all tolerated/ignored by other methods)
    "perspectives": {
        "constructive": "Paris anchors French governance and culture.",
        "destructive": "Centralization in Paris created regional inequality.",
        "systemic": "Paris functions as a hub within European networks.",
        "minimalist": "Paris is the capital and historical center.",
    },
    "constructive": "Paris anchors French governance and culture.",
    "destructive": "Centralization in Paris created regional inequality.",
    "systemic": "Paris functions as a hub within European networks.",
    "minimalist": "Paris is the capital and historical center.",
    "thesis": "Paris is the enduring capital of France.",
    "antithesis": "Centralization has drawbacks.",
    "synthesis_text": "Paris remains central despite regional tensions.",
    "answer": "Paris is the capital of France.",
    "answers": ["Paris is the capital of France."],
    "candidates": [
        {"content": "Paris is the capital of France.", "model": "mock"},
    ],
    "hypotheses": [{"id": "h1", "statement": "Paris is the capital due to its central location.", "prior_probability": 0.8}],
    "clusters": [{"name": "capital cities", "ideas": [{"title": "Paris", "keep": True, "description": "Capital of France."}]}],
    "developments": [{"title": "Paris as a political center", "content": "Paris has served as the political center of France for centuries."}],
    "ideas": [{"id": "1", "title": "Paris is the capital.", "probability": 0.9, "creativity_tier": "conventional", "core_insight": "Paris serves as France's capital city.", "keep": True}],
    "claims": [{"claim": "Paris is the capital.", "label": "verified"}],
    "key_claims": [{"claim": "Paris is the capital of France.", "evidence": "Historical records"}],
    "modules": [],
    "adaptations_required": [],
    "adapted_modules": [],
    "final_answer": "Paris is the capital of France.",
    "draft_answer": "Paris is the capital of France.",
    "assembled_answer": "Paris is the capital of France.",
    "intermediate_steps": [],
    "interpretation": "Paris is the capital.",
    "code": "",
    "files": [],
    "converged": True,
    "confidence": 0.9,
    "decision": "Paris is the capital.",
    "article": "Paris is the capital of France.",
    "final_article": "Paris is the capital of France.",
}

_JSON_BLOB = json.dumps(_RICH_JSON)


def _mock_response(role: str) -> str:
    """Return a deterministic, parser-friendly response for the given role."""
    if role in _JSON_ROLES:
        return "```json\n" + _JSON_BLOB + "\n```"
    # All other roles: return JSON too. Phases that expect prose will fall back
    # to extract_solution_prose / core_solution, and phases that expect JSON
    # parse cleanly. This maximizes coverage with a single payload.
    return "```json\n" + _JSON_BLOB + "\n```"


@pytest.fixture
def mock_router_call():
    """Patch ProviderRouter.call to return deterministic, parser-friendly output."""
    async def _fake_call(self, role: str, system_prompt: str, user_prompt: str, **kwargs: Any):
        return _mock_response(role), {
            "model": getattr(getattr(self, "primary", None), "model", "mock-model"),
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    with patch("reasoner.infrastructure.llm.router.ProviderRouter.call", _fake_call):
        yield


@pytest.fixture
def mock_subagents_off():
    """Ensure the subagent paths (which make extra real calls) are disabled."""
    # USE_PHASE_SUBAGENTS defaults are False; patch defensively so the test is
    # independent of the env the machine happens to have.
    with patch("reasoner.pipeline.USE_PHASE_SUBAGENTS", {
        "enhancement": False, "decomposition": False, "critique": False,
        "synthesis": False, "search": False,
    }):
        yield


def _build_pipeline(preset_id: str) -> ReasonerPipeline:
    _, router = _PRESET_SERVICE.build_router(preset_id)
    return ReasonerPipeline(
        router=router,
        preset_name=preset_id,
        top_k=2,
        parallel_perspectives=True,
        verbose=False,
        source_type="general",
    )


class TestAllBudgetPresetsE2E:
    """Every budget preset must run the full pipeline to a valid solution."""

    @pytest.mark.parametrize("preset_id", ALL_BUDGET_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_preset_runs_to_completion(self, preset_id, mock_router_call, mock_subagents_off):
        pipeline = _build_pipeline(preset_id)
        state = await pipeline.run(_SIMPLE_PROBLEM)

        # The pipeline must produce a synthesis — the single most important
        # contract for a preset "running e2e without bugs".
        assert state.final_solution is not None, (
            f"{preset_id}: pipeline finished without a final_solution"
        )
        assert state.final_solution.core_solution, (
            f"{preset_id}: final_solution.core_solution is empty"
        )
        assert len(state.final_solution.core_solution) > 10, (
            f"{preset_id}: final_solution.core_solution is too short"
        )

        # No critical pipeline-processing errors should be recorded.
        critical = [e for e in state.errors if "Pipeline processing error" in e]
        assert not critical, f"{preset_id}: critical errors: {critical}"
