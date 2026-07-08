"""Unit tests for ACR Phase 1: Call-Level Telemetry.

Tests domain value objects and telemetry store query logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from reasoner.domain.telemetry import LLMCallTelemetry, ModelRoleStats


class TestLLMCallTelemetry:
    """LLMCallTelemetry value object construction and validation."""

    def test_minimal_construction(self):
        """A minimal telemetry event can be created with required fields."""
        event = LLMCallTelemetry(
            call_id=str(uuid.uuid4()),
            run_id="run-001",
            timestamp="2026-07-08T12:00:00Z",
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
            vendor="anthropic",
            bloc="US",
        )
        assert event.call_id is not None
        assert event.model_id == "claude-sonnet"
        assert event.role == "constructive"
        assert event.success is True
        assert event.is_fallback is False
        assert event.json_valid is None
        assert event.critique_score is None
        assert event.stress_test_pass is None

    def test_full_construction(self):
        """All fields can be specified, including optionals."""
        event = LLMCallTelemetry(
            call_id=str(uuid.uuid4()),
            run_id="run-001",
            timestamp="2026-07-08T12:00:00Z",
            model_id="deepseek-v4-pro",
            role="scoring",
            preset_id="debate-premium",
            method="debate",
            phase=3,
            latency_ms=5678.9,
            input_tokens=2000,
            output_tokens=800,
            cost_usd=0.015,
            success=True,
            json_valid=True,
            is_fallback=True,
            fallback_reason="timeout",
            circuit_state="half_open",
            critique_score=8.5,
            stress_test_pass=True,
            vendor="deepseek",
            bloc="CN",
        )
        assert event.json_valid is True
        assert event.is_fallback is True
        assert event.fallback_reason == "timeout"
        assert event.circuit_state == "half_open"
        assert event.critique_score == 8.5
        assert event.stress_test_pass is True
        assert event.bloc == "CN"

    def test_failure_event(self):
        """A failed call records success=False and the reason."""
        event = LLMCallTelemetry(
            call_id=str(uuid.uuid4()),
            run_id="run-001",
            timestamp="2026-07-08T12:00:00Z",
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
        assert event.success is False
        assert event.fallback_reason == "timeout"
        assert event.circuit_state == "open"
        assert event.cost_usd == 0.0
        assert event.output_tokens == 0

    def test_frozen_immutable(self):
        """Telemetry events are frozen and cannot be modified."""
        event = LLMCallTelemetry(
            call_id=str(uuid.uuid4()),
            run_id="run-001",
            timestamp="2026-07-08T12:00:00Z",
            model_id="gpt-5",
            role="destructive",
            preset_id="multi-perspective-budget",
            method="multi-perspective",
            phase=2,
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.001,
            success=True,
            vendor="openai",
            bloc="US",
        )
        with pytest.raises(AttributeError):
            event.success = False  # type: ignore[misc]


class TestModelRoleStats:
    """ModelRoleStats aggregation value object."""

    def test_empty_stats(self):
        """Empty stats have zero defaults."""
        stats = ModelRoleStats(model_id="claude-sonnet", role="constructive")
        assert stats.model_id == "claude-sonnet"
        assert stats.role == "constructive"
        assert stats.total_calls == 0
        assert stats.success_rate == 0.0
        assert stats.avg_critique_score is None
        assert stats.sample_count == 0

    def test_full_stats(self):
        """All aggregation fields are populated."""
        stats = ModelRoleStats(
            model_id="claude-sonnet",
            role="constructive",
            total_calls=100,
            successful_calls=95,
            fallback_calls=5,
            avg_latency_ms=1500.0,
            p95_latency_ms=3000.0,
            avg_input_tokens=500,
            avg_output_tokens=200,
            avg_cost_usd=0.003,
            total_cost_usd=0.30,
            success_rate=0.95,
            json_valid_rate=0.98,
            avg_critique_score=8.2,
            stress_test_pass_rate=0.90,
            vendor="anthropic",
            bloc="US",
            sample_count=100,
        )
        assert stats.success_rate == 0.95
        assert stats.total_cost_usd == 0.30
        assert stats.avg_critique_score == 8.2
        assert stats.sample_count == 100

    def test_frozen_immutable(self):
        """ModelRoleStats is frozen."""
        stats = ModelRoleStats(model_id="gpt-5", role="scoring")
        with pytest.raises(AttributeError):
            stats.model_id = "other"
