"""Tests for MethodState dict wrapper and backward-compatible aliases."""

from __future__ import annotations

import tempfile
from pathlib import Path

from reasoner.models import (
    PipelineCore,
    PipelineState,
    TaskType,
    load,
    save,
)


def test_method_state_bayesian() -> None:
    """Set bayesian_state, read via property + method_state.get."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.bayesian_state = {"prior": 0.5, "likelihood": 0.8}
    assert state.bayesian_state == {"prior": 0.5, "likelihood": 0.8}
    assert state.method_state.get("bayesian") == {"prior": 0.5, "likelihood": 0.8}


def test_method_state_debate_rounds() -> None:
    """Set debate_rounds, verify alias stores in nested dict."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.debate_rounds = [{"round": 1, "content": "opening"}]
    assert state.debate_rounds == [{"round": 1, "content": "opening"}]
    assert state.method_state.data["debate"]["rounds"] == [{"round": 1, "content": "opening"}]


def test_method_state_default_empty() -> None:
    """Unset property returns empty dict/list."""
    state = PipelineState(core=PipelineCore(problem="test"))
    assert state.bayesian_state == {}
    assert state.debate_rounds == []
    assert state.jury_guidelines == []
    assert state.scientific_state == {}


def test_method_state_new_method() -> None:
    """method_state.set('new_method', {...}) works."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.method_state.set("new_method", {"key": "value"})
    assert state.method_state.get("new_method") == {"key": "value"}


def test_load_old_state_file() -> None:
    """_from_dict with old-format JSON (flat method fields)."""
    old_data = {
        "problem": "old test",
        "task_type": "analytical",
        "bayesian_state": {"prior": 0.3},
        "debate_rounds": [{"round": 1}],
        "scientific_state": {},  # empty — should be skipped
        "coding_state": {"language": "python"},
    }
    state = PipelineState._from_dict(old_data)
    assert state.problem == "old test"
    assert state.bayesian_state == {"prior": 0.3}
    assert state.debate_rounds == [{"round": 1}]
    assert state.coding_state == {"language": "python"}
    # Empty scientific_state should not be in method_state
    assert "scientific" not in state.method_state.data


def test_to_context_dict_no_methods() -> None:
    """Context dict doesn't include empty method_state."""
    state = PipelineState(core=PipelineCore(problem="test"))
    ctx = state.to_context_dict()
    # Empty method states should not appear
    assert "bayesian_state" not in ctx
    assert "debate_rounds" not in ctx


def test_to_context_dict_with_methods() -> None:
    """Context dict includes non-empty method states."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.bayesian_state = {"prior": 0.5}
    state.debate_rounds = [{"round": 1}]
    ctx = state.to_context_dict()
    assert ctx["bayesian_state"] == {"prior": 0.5}
    assert ctx["debate_rounds"] == [{"round": 1}]


def test_jury_guidelines_and_weighted_ranking() -> None:
    """Jury fields are stored in nested jury dict."""
    state = PipelineState(core=PipelineCore(problem="test"))
    state.jury_guidelines = ["be fair", "be thorough"]
    state.jury_weighted_ranking = ["gen_1", "gen_2"]
    assert state.method_state.data["jury"]["guidelines"] == ["be fair", "be thorough"]
    assert state.method_state.data["jury"]["weighted_ranking"] == ["gen_1", "gen_2"]


def test_save_load_roundtrip() -> None:
    """PipelineState with method_state serializes and deserializes correctly."""
    state = PipelineState(
        core=PipelineCore(
            problem="roundtrip test",
            task_type=TaskType.ANALYTICAL,
        ),
    )
    state.bayesian_state = {"prior": 0.7}
    state.debate_rounds = [{"round": 1, "content": "hello"}]

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        save(state, str(path))
        loaded = load(str(path))

    assert loaded.problem == "roundtrip test"
    assert loaded.bayesian_state == {"prior": 0.7}
    assert loaded.debate_rounds == [{"round": 1, "content": "hello"}]
    assert loaded.task_type == TaskType.ANALYTICAL
