"""Tests for PerspectiveRegistry runtime extensibility."""

from __future__ import annotations

import pytest

from reasoner.models import (
    PerspectiveRegistry,
    PerspectiveType,
    SolutionCandidate,
    CritiqueScore,
)


def test_known_perspectives_validate() -> None:
    """constructive, destructive pass validation."""
    assert PerspectiveRegistry.validate("constructive") is True
    assert PerspectiveRegistry.validate("destructive") is True
    assert PerspectiveRegistry.validate("systemic") is True
    assert PerspectiveRegistry.validate("minimalist") is True


def test_runtime_registered_perspective() -> None:
    """'financial' registered → validates."""
    PerspectiveRegistry.register("financial", "Financial analysis perspective")
    assert PerspectiveRegistry.validate("financial") is True
    # Cleanup for other tests
    PerspectiveRegistry._known.pop("financial", None)
    PerspectiveRegistry.validate.cache_clear()


def test_unknown_perspective_rejected() -> None:
    """'nonexistent' fails validation."""
    assert PerspectiveRegistry.validate("nonexistent") is False


def test_enum_still_works() -> None:
    """PerspectiveType.CONSTRUCTIVE still valid."""
    assert PerspectiveType.CONSTRUCTIVE == "constructive"
    assert PerspectiveType("constructive") == PerspectiveType.CONSTRUCTIVE


def test_coerce_runtime_perspective() -> None:
    """coerce returns string for registered-only."""
    PerspectiveRegistry.register("financial", "Financial analysis perspective")
    result = PerspectiveRegistry.coerce("financial")
    assert result == "financial"
    assert isinstance(result, str)
    # Cleanup
    PerspectiveRegistry._known.pop("financial", None)
    PerspectiveRegistry.validate.cache_clear()


def test_coerce_enum_for_known() -> None:
    """coerce returns enum for built-in perspectives."""
    result = PerspectiveRegistry.coerce("constructive")
    assert result == PerspectiveType.CONSTRUCTIVE
    assert isinstance(result, PerspectiveType)


def test_coerce_unknown_raises() -> None:
    """coerce raises ValueError for unknown perspective."""
    with pytest.raises(ValueError, match="Unknown perspective"):
        PerspectiveRegistry.coerce("nonexistent")


def test_solution_candidate_post_init() -> None:
    """SolutionCandidate coerces string perspective via __post_init__."""
    sc = SolutionCandidate(
        perspective="constructive",
        content="test",
        key_insights=["a"],
        model_used="gpt-4",
    )
    assert sc.perspective == PerspectiveType.CONSTRUCTIVE


def test_solution_candidate_runtime_perspective() -> None:
    """SolutionCandidate accepts runtime-registered perspective."""
    PerspectiveRegistry.register("financial", "Financial analysis perspective")
    sc = SolutionCandidate(
        perspective="financial",
        content="test",
        key_insights=["a"],
        model_used="gpt-4",
    )
    assert sc.perspective == "financial"
    # Cleanup
    PerspectiveRegistry._known.pop("financial", None)
    PerspectiveRegistry.validate.cache_clear()


def test_critique_score_post_init() -> None:
    """CritiqueScore coerces string perspective via __post_init__."""
    cs = CritiqueScore(
        perspective="destructive",
        logical_consistency=8.0,
        evidence_support=7.0,
        failure_resilience=6.0,
        feasibility=9.0,
        bias_flags=[],
        steel_man="strong case",
    )
    assert cs.perspective == PerspectiveType.DESTRUCTIVE
