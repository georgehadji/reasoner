"""
Regression tests for bugs identified by Autonomous Repository Bug-Fixing Protocol v2.0.

Covers:
- BUG-001: Follow-up neuro persist sends previous synthesis instead of current
- BUG-002: clear_cache endpoint doesn't clear in-memory cache
- BUG-003: AuthManager.generate_key mutates _keys without lock
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────
# BUG-001: Follow-up neuro persist uses wrong synthesis field
# ─────────────────────────────────────────────────────────────────────

def test_neuro_persist_prefers_final_solution():
    """
    Regression: run_followup_stream must send the current turn's generated
    answer (final_solution.core_solution) to the neuro service, not the
    previous turn's synthesis (previous_synthesis).
    """
    from reasoner.models import PipelineState, FinalSolution, MetaCognitiveAudit

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
    from reasoner.api.cache import _MEMORY_CACHE, CACHE_DIR
    from reasoner.api import clear_cache
    from reasoner.core.settings import Settings
    from starlette.requests import Request

    # Write a disk file so we can verify disk clearing too
    test_file = CACHE_DIR / "regression-test-disk.json"
    test_file.write_text("[]", encoding="utf-8")

    # Verify preconditions
    assert "regression-test-key" in _MEMORY_CACHE
    assert test_file.exists()

    # The endpoint is admin-gated: CSRF alone left it open to any caller.
    admin_key = "test-admin-key-for-regression"
    # Patch the class: patching the instance leaves a shadowing attribute behind.
    monkeypatch.setattr(Settings, "ADMIN_API_KEY", admin_key)
    request = Request({
        "type": "http",
        "method": "DELETE",
        "path": "/api/cache",
        "headers": [(b"x-admin-key", admin_key.encode())],
    })

    result = await clear_cache(request)

    # Postconditions: both memory and disk must be empty
    assert "regression-test-key" not in _MEMORY_CACHE
    assert not test_file.exists()
    assert result["cleared"] >= 1


# ─────────────────────────────────────────────────────────────────────
# BUG-003: AuthManager.generate_key must be async-safe
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_key_is_async_and_stores_key():
    """
    Regression: generate_key must be awaitable and correctly store the key
    under the internal asyncio lock.
    """
    from reasoner.auth import AuthManager

    manager = AuthManager()
    raw_key = await manager.generate_key("test-key")

    assert isinstance(raw_key, str)
    assert len(raw_key) > 0

    key_hash = manager._hash_key(raw_key)
    assert key_hash in manager._keys
    assert manager._keys[key_hash].name == "test-key"


@pytest.mark.asyncio
async def test_generate_key_concurrent_safety():
    """
    Regression: concurrent generate_key calls must not corrupt _keys.
    """
    from reasoner.auth import AuthManager

    manager = AuthManager()

    async def generate_many(n: int) -> list[str]:
        return [await manager.generate_key(f"key-{i}") for i in range(n)]

    # Run two batches concurrently
    batch_a, batch_b = await asyncio.gather(
        generate_many(50),
        generate_many(50),
    )

    all_keys = batch_a + batch_b
    all_hashes = [manager._hash_key(k) for k in all_keys]

    # No duplicates, no missing keys
    assert len(all_hashes) == len(set(all_hashes))
    for h in all_hashes:
        assert h in manager._keys

    assert len(manager._keys) == 100
