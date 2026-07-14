"""Unit tests for the Phase Quality Monitor — criteria and state reset functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from reasoner.quality.criteria import (
    PhaseQualityResult,
    evaluate_rules,
    reset_phase_state,
)
from reasoner.core.constants import (
    get_quality_judge_model,
    get_quality_judge_threshold,
    QUALITY_JUDGE_MODELS,
    QUALITY_JUDGE_THRESHOLDS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Minimal PipelineState stub — only the fields criteria.py reads
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _State:
    task_type: Any = None
    decomposition: Any = None
    candidates: list = field(default_factory=list)
    scores: list = field(default_factory=list)
    top_candidates: list = field(default_factory=list)
    stress_results: list = field(default_factory=list)
    final_solution: Any = None
    writing_state: dict = field(default_factory=dict)
    phase_tokens: dict = field(default_factory=dict)
    quality_hints: dict = field(default_factory=dict)


def _candidate(content: str) -> Any:
    c = MagicMock()
    c.content = content
    return c


def _score(total: float) -> Any:
    s = MagicMock()
    s.total = total
    return s


def _stress(survival_rate: float) -> Any:
    r = MagicMock()
    r.survival_rate = survival_rate
    return r


def _solution(core: str, insights: list | None = None) -> Any:
    sol = MagicMock()
    sol.core_solution = core
    sol.critical_insights = insights or []
    return sol


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────

def test_classification_pass():
    state = _State(task_type="ANALYTICAL")
    result = evaluate_rules("Classification", state)
    assert result.passed


def test_classification_fail():
    state = _State(task_type=None)
    result = evaluate_rules("Classification", state)
    assert not result.passed


# ─────────────────────────────────────────────────────────────────────────────
# Decomposition
# ─────────────────────────────────────────────────────────────────────────────

def test_decomposition_pass():
    state = _State(decomposition=["sub1", "sub2"])
    assert evaluate_rules("Decomposition", state).passed


def test_decomposition_fail_none():
    state = _State(decomposition=None)
    assert not evaluate_rules("Decomposition", state).passed


def test_decomposition_fail_empty():
    state = _State(decomposition=[])
    assert not evaluate_rules("Decomposition", state).passed


# ─────────────────────────────────────────────────────────────────────────────
# Perspectives
# ─────────────────────────────────────────────────────────────────────────────

def test_perspectives_pass():
    state = _State(candidates=[_candidate("A" * 100), _candidate("B" * 100)])
    result = evaluate_rules("Perspectives", state)
    assert result.passed


def test_perspectives_fail_empty():
    state = _State(candidates=[])
    assert not evaluate_rules("Perspectives", state).passed


def test_perspectives_all_thin():
    state = _State(candidates=[_candidate("Hi"), _candidate("Ok")])
    result = evaluate_rules("Perspectives", state)
    assert not result.passed


def test_perspectives_some_thin():
    state = _State(candidates=[_candidate("A" * 100), _candidate("short")])
    result = evaluate_rules("Perspectives", state)
    assert result.passed
    assert result.score < 9.0


# ─────────────────────────────────────────────────────────────────────────────
# Critique & Pruning
# ─────────────────────────────────────────────────────────────────────────────

def test_critique_pass():
    state = _State(scores=[_score(7.0)], top_candidates=[_candidate("ok" * 20)])
    assert evaluate_rules("Critique & Pruning", state).passed


def test_critique_fail_no_scores():
    state = _State(scores=[], top_candidates=[_candidate("x")])
    assert not evaluate_rules("Critique & Pruning", state).passed


def test_critique_fail_bad_scores():
    state = _State(scores=[_score(15.0)], top_candidates=[_candidate("x")])
    result = evaluate_rules("Critique & Pruning", state)
    assert not result.passed


# ─────────────────────────────────────────────────────────────────────────────
# Stress Testing
# ─────────────────────────────────────────────────────────────────────────────

def test_stress_pass():
    state = _State(stress_results=[_stress(0.8)])
    assert evaluate_rules("Stress Testing", state).passed


def test_stress_fail_empty():
    state = _State(stress_results=[])
    assert not evaluate_rules("Stress Testing", state).passed


def test_stress_fail_bad_rate():
    state = _State(stress_results=[_stress(1.5)])
    assert not evaluate_rules("Stress Testing", state).passed


# ─────────────────────────────────────────────────────────────────────────────
# Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def test_synthesis_pass():
    state = _State(final_solution=_solution("x" * 150, insights=["insight"]))
    assert evaluate_rules("Synthesis", state).passed


def test_synthesis_fail_none():
    state = _State(final_solution=None)
    assert not evaluate_rules("Synthesis", state).passed


def test_synthesis_fail_short_core():
    state = _State(final_solution=_solution("short"))
    assert not evaluate_rules("Synthesis", state).passed


def test_synthesis_no_insights_partial_pass():
    state = _State(final_solution=_solution("x" * 150, insights=[]))
    result = evaluate_rules("Synthesis", state)
    assert result.passed
    assert result.score < 9.0


# ─────────────────────────────────────────────────────────────────────────────
# Writing phases
# ─────────────────────────────────────────────────────────────────────────────

def test_decompose_topic_pass():
    state = _State(writing_state={"subquestions": ["q1", "q2"]})
    assert evaluate_rules("Decompose Topic", state).passed


def test_decompose_topic_fail():
    state = _State(writing_state={})
    assert not evaluate_rules("Decompose Topic", state).passed


def test_retrieve_sources_pass():
    state = _State(writing_state={"retrieved_sources": [{"title": "t"}]})
    assert evaluate_rules("Retrieve Sources", state).passed


def test_retrieve_sources_fail():
    state = _State(writing_state={})
    result = evaluate_rules("Retrieve Sources", state)
    assert not result.passed


def test_final_assembly_pass():
    state = _State(writing_state={"final_article": "x" * 600})
    assert evaluate_rules("Final Assembly", state).passed


def test_final_assembly_fail_short():
    state = _State(writing_state={"final_article": "short"})
    assert not evaluate_rules("Final Assembly", state).passed


# ─────────────────────────────────────────────────────────────────────────────
# Unknown phase — should pass with default score
# ─────────────────────────────────────────────────────────────────────────────

def test_unknown_phase_passes():
    state = _State()
    result = evaluate_rules("Some Unknown Phase", state)
    assert result.passed
    assert result.score == 8.0


# ─────────────────────────────────────────────────────────────────────────────
# State reset
# ─────────────────────────────────────────────────────────────────────────────

def test_reset_perspectives():
    state = _State(candidates=[_candidate("x" * 100)])
    reset_phase_state("Perspectives", state)
    assert state.candidates == []


def test_reset_synthesis():
    state = _State(final_solution=_solution("x" * 200))
    reset_phase_state("Synthesis", state)
    assert state.final_solution is None


def test_reset_decompose_topic():
    state = _State(writing_state={"subquestions": ["q1"], "other": "val"})
    reset_phase_state("Decompose Topic", state)
    assert "subquestions" not in state.writing_state
    assert state.writing_state.get("other") == "val"


def test_reset_clears_phase_tokens():
    state = _State(phase_tokens={"Phase Perspectives attempt": {"input": 10, "output": 20}})
    reset_phase_state("Perspectives", state)
    assert state.phase_tokens == {}


# ─────────────────────────────────────────────────────────────────────────────
# Context Vetting / Deep Read rules (Improvement 6)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _StateWithContext(_State):
    vetted_context: list = field(default_factory=list)
    context_quality: str = "unknown"


def test_context_vetting_pass():
    state = _StateWithContext(
        vetted_context=[{"url": "http://example.com", "summary": "A very detailed summary here"}],
        context_quality="good",
    )
    result = evaluate_rules("Context Vetting", state)
    assert result.passed
    assert result.score == 9.0


def test_context_vetting_fail_empty():
    state = _StateWithContext(vetted_context=[], context_quality="missing")
    result = evaluate_rules("Context Vetting", state)
    assert not result.passed


def test_context_vetting_contaminated():
    state = _StateWithContext(
        vetted_context=[{"url": "http://x.com", "summary": "bad"}],
        context_quality="contaminated",
    )
    result = evaluate_rules("Context Vetting", state)
    assert not result.passed


def test_context_vetting_partial():
    state = _StateWithContext(
        vetted_context=[{"url": "http://x.com", "summary": "ok"}],
        context_quality="partial",
    )
    result = evaluate_rules("Context Vetting", state)
    assert result.passed
    assert result.score == 7.0


def test_deep_read_pass():
    state = _StateWithContext(
        vetted_context=[{"url": "http://x.com", "summary": "This is a detailed summary of the source."}],
        context_quality="good",
    )
    assert evaluate_rules("Deep Read", state).passed


def test_deep_read_fail_empty():
    state = _StateWithContext(vetted_context=[], context_quality="unknown")
    assert not evaluate_rules("Deep Read", state).passed


def test_deep_read_fail_no_summaries():
    state = _StateWithContext(
        vetted_context=[{"url": "http://x.com", "summary": ""}],
        context_quality="good",
    )
    assert not evaluate_rules("Deep Read", state).passed


# ─────────────────────────────────────────────────────────────────────────────
# Tier-aware judge model + threshold (Improvement 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_judge_model_premium():
    assert get_quality_judge_model("multi-perspective-premium") == QUALITY_JUDGE_MODELS["premium"]


def test_judge_model_budget():
    assert get_quality_judge_model("debate-budget") == QUALITY_JUDGE_MODELS["budget"]


def test_judge_model_default():
    assert get_quality_judge_model("some-unknown-preset") == QUALITY_JUDGE_MODELS["default"]


def test_judge_threshold_premium():
    assert get_quality_judge_threshold("jury-premium") == QUALITY_JUDGE_THRESHOLDS["premium"]


def test_judge_threshold_budget():
    assert get_quality_judge_threshold("research-budget") == QUALITY_JUDGE_THRESHOLDS["budget"]


def test_judge_threshold_default():
    assert get_quality_judge_threshold("something") == QUALITY_JUDGE_THRESHOLDS["default"]


def test_premium_threshold_higher_than_budget():
    assert QUALITY_JUDGE_THRESHOLDS["premium"] > QUALITY_JUDGE_THRESHOLDS["budget"]
