"""Tests for PipelineState Core/Meta/Remainder split."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from reasoner.models import (
    PipelineState,
    PipelineCore,
    PipelineMeta,
    PipelineRemainder,
    TaskType,
    SolutionCandidate,
    PerspectiveType,
)


def test_property_alias_read() -> None:
    """state.problem == state.core.problem"""
    state = PipelineState(core=PipelineCore(problem="test"))
    assert state.problem == "test"
    assert state.problem == state.core.problem


def test_property_alias_write() -> None:
    """state.problem = 'x' → state.core.problem == 'x'"""
    state = PipelineState(core=PipelineCore(problem=""))
    state.problem = "new problem"
    assert state.core.problem == "new problem"


def test_core_only_serialization() -> None:
    """PipelineCore serializes to dict."""
    core = PipelineCore(problem="test", task_type=TaskType.ANALYTICAL)
    state = PipelineState(core=core)
    d = state.to_dict()
    assert d["core"]["problem"] == "test"
    assert d["core"]["task_type"] == "analytical"


def test_meta_only_serialization() -> None:
    """PipelineMeta serializes to dict."""
    meta = PipelineMeta(preset_name="multi-perspective", context_quality="good")
    state = PipelineState(core=PipelineCore(problem="test"), meta=meta)
    d = state.to_dict()
    assert d["meta"]["preset_name"] == "multi-perspective"
    assert d["meta"]["context_quality"] == "good"


def test_remainder_only_serialization() -> None:
    """PipelineRemainder serializes to dict."""
    rem = PipelineRemainder(reflexion_memory=["insight 1"])
    state = PipelineState(core=PipelineCore(problem="test"), remainder=rem)
    d = state.to_dict()
    assert d["remainder"]["reflexion_memory"] == ["insight 1"]


def test_full_roundtrip() -> None:
    """PipelineState → dict → PipelineState."""
    state = PipelineState(
        core=PipelineCore(
            problem="roundtrip test",
            task_type=TaskType.ANALYTICAL,
        ),
        meta=PipelineMeta(
            preset_name="multi-perspective",
            method="multi_perspective",
        ),
    )
    state.candidates = [
        SolutionCandidate(
            perspective=PerspectiveType.CONSTRUCTIVE,
            content="test",
            key_insights=["a"],
            model_used="gpt-4",
        )
    ]

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        state.save(str(path))
        loaded = PipelineState.load(str(path))

    assert loaded.problem == "roundtrip test"
    assert loaded.task_type == TaskType.ANALYTICAL
    assert loaded.preset_name == "multi-perspective"
    assert loaded.method == "multi_perspective"
    assert len(loaded.candidates) == 1
    assert loaded.candidates[0].perspective == PerspectiveType.CONSTRUCTIVE


def test_backward_compat_solution_getter() -> None:
    """state.synthesis still returns dict."""
    from reasoner.models import FinalSolution, MetaCognitiveAudit

    state = PipelineState(core=PipelineCore(problem="test"))
    assert state.synthesis is None

    state.final_solution = FinalSolution(
        core_solution="solution text",
        critical_insights=["insight 1"],
        action_blueprint=[],
        open_questions=[],
        claim_labels={},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="",
            dominant_bias="",
            remaining_uncertainty="",
            assumption_failure_impact="",
            non_obvious_insight="",
        ),
    )
    assert state.synthesis == {
        "core_solution": "solution text",
        "critical_insights": ["insight 1"],
    }


def test_load_old_format_state_file() -> None:
    """Old flat-format state file migrates to new structure."""
    old_data = {
        "problem": "old problem",
        "task_type": "analytical",
        "preset_name": "multi-perspective",
        "phase_logs": ["[PHASE-1] started"],
        "reflexion_memory": ["insight"],
        "candidates": [
            {
                "perspective": "constructive",
                "content": "test",
                "key_insights": ["a"],
                "model_used": "gpt-4",
            }
        ],
    }
    state = PipelineState._from_dict(old_data)
    assert state.problem == "old problem"
    assert state.task_type == TaskType.ANALYTICAL
    assert state.preset_name == "multi-perspective"
    assert state.phase_logs == ["[PHASE-1] started"]
    assert state.reflexion_memory == ["insight"]
    assert len(state.candidates) == 1
    assert state.candidates[0].content == "test"


def test_meta_fields_via_alias() -> None:
    """Meta fields accessible via property aliases."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.phase_logs = ["log 1", "log 2"]
    state.phase_durations = {"phase_1": 1.5}
    state.quality_hints = {"phase_1": "hint"}
    assert state.meta.phase_logs == ["log 1", "log 2"]
    assert state.meta.phase_durations == {"phase_1": 1.5}
    assert state.meta.quality_hints == {"phase_1": "hint"}


def test_remainder_fields_via_alias() -> None:
    """Remainder fields accessible via property aliases."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.web_discovery_results = [{"title": "Test"}]
    state.vetted_context = [{"flag": "ok"}]
    assert state.remainder.web_discovery_results == [{"title": "Test"}]
    assert state.remainder.vetted_context == [{"flag": "ok"}]


def test_method_state_still_works_after_split() -> None:
    """MethodState aliases still function after Core/Meta split."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.bayesian_state = {"prior": 0.5}
    state.debate_rounds = [{"round": 1}]
    assert state.method_state.data["bayesian"] == {"prior": 0.5}
    assert state.method_state.data["debate"]["rounds"] == [{"round": 1}]
