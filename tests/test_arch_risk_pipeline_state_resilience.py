"""
Architecture Risk: PipelineState deserialization resilience.

Tests that PipelineState survives truncated, corrupt, and edge-case
state files without crashing. Targets the single-point-of-failure
risk identified in the architecture audit (models.py ~1500 lines).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from reasoner.models import (
    PipelineState,
    PipelineCore,
    PipelineMeta,
    PipelineRemainder,
    MethodState,
    CostTrackingState,
    ConversationState,
    save,
    load,
)


def _state_file(data: dict, tmp: Path) -> Path:
    p = tmp / "state.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── Truncated / corrupt input ───────────────────────────────────────


def test_load_missing_required_keys() -> None:
    """Empty dict → PipelineState with all defaults."""
    state = PipelineState._from_dict({})
    assert state.problem == ""
    assert state.task_type is None
    assert state.candidates == []


def test_load_none_values_in_flat_format() -> None:
    """None values in old-format state should not crash."""
    data = {
        "problem": None,
        "task_type": None,
        "candidates": None,
        "scores": None,
        "stress_results": None,
        "final_solution": None,
        "decomposition": None,
    }
    state = PipelineState._from_dict(data)
    # None values are preserved as-is (not coerced to empty string)
    assert state.problem is None
    assert state.task_type is None
    # candidates=None stays None in PipelineCore (no auto-coercion for lists)
    # This is a design choice: None means "not initialized", [] means "initialized empty"
    assert state.candidates is None


def test_load_truncated_candidate_missing_fields() -> None:
    """Candidate dict missing 'content' key should be skipped, not crash."""
    data = {
        "candidates": [
            {"perspective": "constructive"},  # missing: content, key_insights, model_used
            {
                "perspective": "destructive",
                "content": "valid",
                "key_insights": ["a"],
                "model_used": "m",
            },
        ],
    }
    state = PipelineState._from_dict(data)
    # Only the well-formed candidate survives
    assert len(state.candidates) == 1
    assert state.candidates[0].content == "valid"


def test_load_truncated_score_missing_fields() -> None:
    """CritiqueScore dict missing fields should be skipped, not crash."""
    data = {"scores": [{"logical_consistency": 5}]}  # missing all other required fields
    state = PipelineState._from_dict(data)
    assert state.scores == []


def test_load_truncated_stress_result_missing_scenario() -> None:
    """StressTestResult dict missing 'scenario' — ScenarioType.coerce defaults to OPTIMAL."""
    data = {"stress_results": [{"survival_rate": 0.5}]}
    state = PipelineState._from_dict(data)
    # Code is resilient: coerce defaults missing scenario to OPTIMAL
    assert len(state.stress_results) == 1
    assert state.stress_results[0].survival_rate == 0.5
    assert state.stress_results[0].failure_mode == ""
    assert state.stress_results[0].recovery_path == ""


def test_load_truncated_final_solution_missing_fields() -> None:
    """FinalSolution dict missing meta_audit should still load."""
    data = {
        "final_solution": {
            "core_solution": "test",
            "claim_labels": {"claim": "VERIFIED"},
        }
    }
    state = PipelineState._from_dict(data)
    assert state.final_solution is not None
    assert state.final_solution.core_solution == "test"
    # meta_audit should default to empty MetaCognitiveAudit
    assert state.final_solution.meta_audit.most_dangerous_assumption == ""


def test_load_decomposition_with_extra_llm_keys() -> None:
    """Decomposition dict with unknown LLM keys should not crash."""
    data = {
        "decomposition": {
            "causal_chain": ["a → b"],
            "assumptions": [{"text": "X is true", "label": "HYPOTHESIS"}],
            "failure_modes": ["mode1"],
            "critical_sources": [{"title": "src", "url": "http://x"}],
            "unknown_field_from_llm": "should be stripped",
            "another_unknown": 42,
        }
    }
    state = PipelineState._from_dict(data)
    assert state.decomposition is not None
    # The unknown keys should have been filtered out before Decomposition init
    # If _from_dict didn't strip them, this would crash


def test_load_critic_score_truncated() -> None:
    """CriticScore with missing candidate_scores — constructed with empty dict (resilient)."""
    data = {
        "critic_scores": [
            {"critic_id": "c1", "critic_model": "m", "ranking": []},
            # missing candidate_scores entirely
        ]
    }
    state = PipelineState._from_dict(data)
    # Code is resilient: candidate_scores defaults to empty dict via .get()
    assert len(state.critic_scores) == 1
    assert state.critic_scores[0].candidate_scores == {}


def test_load_verification_result_truncated() -> None:
    """VerificationResult with missing fields — BUG-022 FIXED (2026-05-29).
    Previously _from_dict used direct subscript vr['claim'] which raised KeyError.
    Now uses .get() fallbacks + try/except, matching stress_results pattern."""
    data = {
        "verification_results": [{"verdict": "VERIFIED"}]
        # missing: claim, source_generator, evidence, confidence
    }
    # BUG-022 FIXED: truncated verification entries no longer crash.
    # Missing fields get safe defaults; the one provided field ("VERIFIED") is preserved.
    state = PipelineState._from_dict(data)
    assert len(state.verification_results) == 1
    vr = state.verification_results[0]
    assert vr.claim == ""           # missing → empty string default
    assert vr.source_generator == ""  # missing → empty string default
    assert vr.verdict.value == "VERIFIED"  # the one field we did provide
    assert vr.evidence == ""        # missing → empty string default
    assert vr.confidence == 0.0     # missing → 0.0 default


def test_load_generation_candidate_truncated() -> None:
    """GenerationCandidate with missing fields — re-raises TypeError
    (intentional: ORCHESTRATED method data is critical). Covers the
    'confidence_vs_accuracy_penalty' field regression from BUG-021."""
    data = {
        "generation_candidates": [
            {
                "generator_id": "gen1",
                "model_used": "m",
                "solution": "ok",
            }
            # missing: confidence, key_claims, approach_summary
        ]
    }
    # Should raise because GenerationCandidate has no defaults
    with pytest.raises(TypeError):
        PipelineState._from_dict(data)


def test_load_stress_result_with_invalid_scenario() -> None:
    """StressTestResult with invalid scenario name → falls back to ADVERSARIAL."""
    data = {
        "stress_results": [
            {
                "scenario": "nonexistent_scenario",
                "survival_rate": 0.5,
                "failure_mode": "f",
                "recovery_path": "r",
            }
        ]
    }
    state = PipelineState._from_dict(data)
    assert len(state.stress_results) == 1
    from reasoner.models import ScenarioType

    assert state.stress_results[0].scenario == ScenarioType.ADVERSARIAL


# ── Roundtrip with edge cases ────────────────────────────────────────


def test_roundtrip_with_attachments() -> None:
    """Attachment data survives save/load."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.attachments = [
        {"filename": "report.pdf", "extracted_text": "PDF content here"}
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))
    assert len(loaded.attachments) == 1
    assert loaded.attachments[0]["filename"] == "report.pdf"


def test_roundtrip_with_errors() -> None:
    """Error list survives save/load."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.errors = ["error 1", "error 2"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))
    assert loaded.errors == ["error 1", "error 2"]


def test_cost_state_roundtrip() -> None:
    """CostTrackingState survives save/load."""
    state = PipelineState(
        cost_state=CostTrackingState(
            total_cost_usd=1.23,
            phase_costs={"phase_1": 0.50},
            detailed_token_usage={"phase_1": {"input": 100, "output": 50}},
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))
    assert loaded.total_cost_usd == 1.23
    assert loaded.phase_costs == {"phase_1": 0.50}


def test_conversation_state_roundtrip() -> None:
    """ConversationState survives save/load."""
    state = PipelineState(
        conversation_state=ConversationState(
            conversation_id="conv-123",
            turn_number=3,
            previous_synthesis="previous answer",
            agent_model="claude-sonnet",
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))
    assert loaded.conversation_id == "conv-123"
    assert loaded.turn_number == 3
    assert loaded.previous_synthesis == "previous answer"
    assert loaded.agent_model == "claude-sonnet"


def test_method_state_roundtrip() -> None:
    """MethodState with nested data survives save/load."""
    state = PipelineState(
        method_state=MethodState(
            data={
                "debate": {"rounds": [{"opening": "x", "rebuttal": "y"}]},
                "jury": {"guidelines": ["g1"], "weighted_ranking": ["a", "b"]},
                "bayesian": {"prior": 0.5},
            }
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))
    assert loaded.debate_rounds == [{"opening": "x", "rebuttal": "y"}]
    assert loaded.jury_guidelines == ["g1"]
    assert loaded.bayesian_state == {"prior": 0.5}


# ── Safety: path traversal ───────────────────────────────────────────


def test_save_rejects_directory_traversal() -> None:
    """save() rejects paths with .."""
    state = PipelineState(core=PipelineCore(problem="test"))
    with pytest.raises(ValueError, match="directory traversal"):
        save(state, "../outside.json")


def test_load_rejects_directory_traversal() -> None:
    """load() rejects paths with .."""
    with pytest.raises(ValueError, match="directory traversal"):
        load("../nonexistent.json")


# ── BUG-021 regression: _from_dict direct subscripts ─────────────────


def test_bug021_regression_truncated_stress_result() -> None:
    """A truncated stress result missing 'scenario' key now uses .get(),
    verified by test_load_truncated_stress_result_missing_scenario above.
    This is the specific BUG-021 scenario: older state file with partial
    stress_results entries."""
    data = {
        "stress_results": [
            {
                # missing 'scenario' entirely — was KeyError before BUG-021 fix
                "survival_rate": 0.8,
                "failure_mode": "test mode",
                "recovery_path": "",
            }
        ]
    }
    # Should not raise KeyError (BUG-021 regression)
    state = PipelineState._from_dict(data)
    assert len(state.stress_results) == 1
    # coerce() produces OPTIMAL (default ScenarioType), not ADVERSARIAL.
    # This is the expected behavior — ScenarioType.coerce("") returns OPTIMAL.
    from reasoner.models import ScenarioType

    assert state.stress_results[0].scenario == ScenarioType.OPTIMAL


def test_old_format_migration_preserves_all_fields() -> None:
    """Old flat format with method_state fields migrates correctly."""
    old_data = {
        "problem": "old-style problem",
        "task_type": "analytical",
        "bayesian_state": {"prior": 0.7},
        "jury_guidelines": ["guideline 1", "guideline 2"],
        "debate_rounds": [{"round": 1, "content": "debate content"}],
        "total_cost_usd": 5.50,
        "phase_costs": {"synthesis": 2.00},
        "conversation_id": "conv-migrated",
        "turn_number": 5,
    }
    state = PipelineState._from_dict(old_data)
    assert state.bayesian_state == {"prior": 0.7}
    assert state.jury_guidelines == ["guideline 1", "guideline 2"]
    assert state.debate_rounds == [{"round": 1, "content": "debate content"}]
    assert state.total_cost_usd == 5.50
    assert state.phase_costs == {"synthesis": 2.00}
    assert state.conversation_id == "conv-migrated"
    assert state.turn_number == 5
