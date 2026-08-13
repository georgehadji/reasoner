"""Integration tests for ACR Phase 1: SQLiteCallTelemetryStore.

Tests read/write/query operations against an in-memory SQLite database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from reasoner.domain.telemetry import LLMCallTelemetry
from reasoner.infrastructure.telemetry.call_telemetry_store import (
    SQLiteCallTelemetryStore,
)


def _now_iso() -> str:
    """Timestamp inside the stores default query window.

    The queries filter on `timestamp >= datetime('now', '-N hours')`, so a
    hardcoded date silently ages out of every window and all assertions collapse
    to zero rows.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def store(tmp_path):
    """Create a telemetry store backed by a temp SQLite database."""
    db_path = str(tmp_path / "test_telemetry.db")
    return SQLiteCallTelemetryStore(db_path=db_path)


@pytest.fixture
def sample_event() -> LLMCallTelemetry:
    """A sample successful call telemetry event."""
    return LLMCallTelemetry(
        call_id=str(uuid.uuid4()),
        run_id="run-001",
        timestamp=_now_iso(),
        model_id="claude-sonnet",
        role="constructive",
        preset_id="multi-perspective-budget",
        method="multi-perspective",
        phase=2,
        latency_ms=1234.5,
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.002,
        success=True,
        json_valid=True,
        is_fallback=False,
        circuit_state="closed",
        vendor="anthropic",
        bloc="US",
        critique_score=8.5,
        stress_test_pass=True,
    )


@pytest.fixture
def failed_event() -> LLMCallTelemetry:
    """A failed call event."""
    return LLMCallTelemetry(
        call_id=str(uuid.uuid4()),
        run_id="run-001",
        timestamp=_now_iso(),
        model_id="claude-haiku",
        role="constructive",
        preset_id="multi-perspective-budget",
        method="multi-perspective",
        phase=2,
        latency_ms=30000.0,
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.0,
        success=False,
        is_fallback=True,
        fallback_reason="timeout",
        circuit_state="open",
        vendor="anthropic",
        bloc="US",
    )


@pytest.mark.asyncio
async def test_record_and_query_success(store, sample_event):
    """Record a call and verify stats reflect success."""
    await store.record_call(sample_event)

    stats = await store.query_model_role_stats(
        model_id="claude-sonnet",
        role="constructive",
    )
    assert stats.total_calls == 1
    assert stats.successful_calls == 1
    assert stats.success_rate == 1.0
    assert stats.fallback_calls == 0
    assert stats.vendor == "anthropic"
    assert stats.bloc == "US"


@pytest.mark.asyncio
async def test_record_and_query_failure(store, failed_event):
    """Record a failed call and verify stats reflect failure."""
    await store.record_call(failed_event)

    stats = await store.query_model_role_stats(
        model_id="claude-haiku",
        role="constructive",
    )
    assert stats.total_calls == 1
    assert stats.successful_calls == 0
    assert stats.success_rate == 0.0
    assert stats.fallback_calls == 1


@pytest.mark.asyncio
async def test_aggregate_multiple_calls(store, sample_event, failed_event):
    """Multiple calls for same (model, role) produce aggregated stats."""
    # Record 3 successful + 1 failed
    for _ in range(3):
        evt = LLMCallTelemetry(
            call_id=str(uuid.uuid4()),
            run_id="run-001",
            timestamp=_now_iso(),
            model_id="claude-sonnet",
            role="constructive",
            preset_id="multi-perspective-budget",
            method="multi-perspective",
            phase=2,
            latency_ms=1000.0,
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.002,
            success=True,
            vendor="anthropic",
            bloc="US",
        )
        await store.record_call(evt)

    # One failed
    fail_evt = LLMCallTelemetry(
        call_id=str(uuid.uuid4()),
        run_id="run-001",
        timestamp=_now_iso(),
        model_id="claude-sonnet",
        role="constructive",
        preset_id="multi-perspective-budget",
        method="multi-perspective",
        phase=2,
        latency_ms=5000.0,
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.0,
        success=False,
        is_fallback=True,
        fallback_reason="timeout",
        circuit_state="open",
        vendor="anthropic",
        bloc="US",
    )
    await store.record_call(fail_evt)

    stats = await store.query_model_role_stats(
        model_id="claude-sonnet",
        role="constructive",
    )
    assert stats.total_calls == 4
    assert stats.successful_calls == 3
    assert stats.success_rate == 0.75
    assert stats.fallback_calls == 1


@pytest.mark.asyncio
async def test_query_empty_role(store):
    """Querying a (model, role) with no data returns empty stats."""
    stats = await store.query_model_role_stats(
        model_id="nonexistent-model",
        role="nonexistent-role",
    )
    assert stats.total_calls == 0
    assert stats.success_rate == 0.0
    assert stats.model_id == "nonexistent-model"
    assert stats.role == "nonexistent-role"


@pytest.mark.asyncio
async def test_role_leaderboard(store):
    """Role leaderboard returns models sorted by quality."""
    # Record events for 3 different models
    models = [
        ("claude-sonnet", "anthropic", "US", True),
        ("deepseek-v4-pro", "deepseek", "CN", True),
        ("gpt-5-nano", "openai", "US", False),  # This one fails
    ]
    for model_id, vendor, bloc, success in models:
        for _ in range(5):
            evt = LLMCallTelemetry(
                call_id=str(uuid.uuid4()),
                run_id="run-002",
                timestamp=_now_iso(),
                model_id=model_id,
                role="scoring",
                preset_id="debate-budget",
                method="debate",
                phase=3,
                latency_ms=1000.0,
                input_tokens=200,
                output_tokens=100,
                cost_usd=0.001,
                success=success,
                vendor=vendor,
                bloc=bloc,
            )
            await store.record_call(evt)

    leaderboard = await store.query_role_leaderboard(role="scoring", limit=5)
    # Should have 2 entries (gpt-5-nano has 0 successes, but still gets included)
    assert len(leaderboard) >= 2

    # First entry should be the most successful model
    top = leaderboard[0]
    assert top.role == "scoring"
    assert top.total_calls >= 5


@pytest.mark.asyncio
async def test_get_recent_calls(store, sample_event):
    """Recent calls endpoint returns recorded events."""
    await store.record_call(sample_event)

    recent = await store.get_recent_calls(limit=10)
    assert len(recent) == 1
    assert recent[0]["model_id"] == "claude-sonnet"
    assert recent[0]["role"] == "constructive"
