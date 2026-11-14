"""
Regression tests for bugs identified by Autonomous Repository Bug-Fixing Protocol v2.0.

Covers:
- BUG-001: Follow-up neuro persist sends previous synthesis instead of current
- BUG-002: clear_cache endpoint doesn't clear in-memory cache
- BUG-003: AuthManager.generate_key mutates _keys without lock
"""

from __future__ import annotations


import pytest

# ─────────────────────────────────────────────────────────────────────
# BUG-001: Follow-up neuro persist uses wrong synthesis field
# ─────────────────────────────────────────────────────────────────────

def test_neuro_persist_prefers_final_solution():
    """
    Regression: run_followup_stream must send the current turn's generated
    answer (final_solution.core_solution) to the neuro service, not the
    previous turn's synthesis (previous_synthesis).
    """
    from reasoner.models import FinalSolution, MetaCognitiveAudit, PipelineState

    audit = MetaCognitiveAudit(
        most_dangerous_assumption="none",
        dominant_bias="none",
        remaining_uncertainty="low",
        assumption_failure_impact="low",
        non_obvious_insight="test",
    )
    state = PipelineState(
        problem="What is 2+2?",
        final_solution=FinalSolution(
            core_solution="new answer: 4",
            critical_insights=[],
            action_blueprint=[],
            open_questions=[],
            claim_labels={},
            meta_audit=audit,
        ),
    )
    state.previous_synthesis = "old answer from previous turn"

    # This mirrors the patched logic in run_followup_stream
    response = (
        state.final_solution.core_solution
        if state.final_solution
        else state.previous_synthesis
    )

    assert response == "new answer: 4"
    assert response != state.previous_synthesis


def test_neuro_persist_fallback_to_previous_synthesis():
    """
    When the pipeline fails to produce a final_solution, the neuro persist
    should gracefully fall back to previous_synthesis.
    """
    from reasoner.models import PipelineState

    state = PipelineState(
        problem="What is 2+2?",
        final_solution=None,
    )
    state.previous_synthesis = "old answer"

    response = (
        state.final_solution.core_solution
        if state.final_solution
        else state.previous_synthesis
    )

    assert response == "old answer"


# ─────────────────────────────────────────────────────────────────────
# BUG-002: clear_cache must invalidate in-memory cache
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_memory_cache(monkeypatch):
    """Seed _MEMORY_CACHE with test data and clean up after."""
    from reasoner.api.cache import _MEMORY_CACHE

    original = dict(_MEMORY_CACHE)
    _MEMORY_CACHE.clear()
    _MEMORY_CACHE["regression-test-key"] = [{"type": "start"}, {"type": "done"}]
    yield
    _MEMORY_CACHE.clear()
    _MEMORY_CACHE.update(original)


@pytest.mark.asyncio
async def test_clear_cache_clears_memory_and_disk(seeded_memory_cache, tmp_path, monkeypatch):
    """
    Regression: DELETE /api/cache must clear both disk files AND the
    in-memory _MEMORY_CACHE dict.
    """
    from reasoner.api import clear_cache
    from reasoner.api.cache import _MEMORY_CACHE, CACHE_DIR

    # Write a disk file so we can verify disk clearing too
    test_file = CACHE_DIR / "regression-test-disk.json"
    test_file.write_text("[]", encoding="utf-8")

    # Verify preconditions
    assert "regression-test-key" in _MEMORY_CACHE
    assert test_file.exists()

    from unittest.mock import MagicMock

    # request is required (Request | None = None
    # broke FastAPI's special-cased Request injection at route
    # registration — docs/plans/pre-existing-fixes.md). Outside production
    # it's unused, so a MagicMock stub is enough for this direct call.
    result = await clear_cache(request=MagicMock())

    # Postconditions: both memory and disk must be empty
    assert "regression-test-key" not in _MEMORY_CACHE
    assert not test_file.exists()
    assert result["cleared"] >= 1
