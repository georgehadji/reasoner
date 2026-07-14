"""Tests for core protocol abstractions (PhaseConfig, PhaseResult)."""

from __future__ import annotations

import time

import pytest

from reasoner.core.protocol import (
    PhaseConfig,
    PhaseResult,
    TemperatureStrategy,
    make_phase_result,
)


class TestPhaseConfig:
    """Test PhaseConfig dataclass."""

    def test_default_values(self):
        config = PhaseConfig()
        assert config.max_tokens > 0
        assert config.temperature == 1.0
        assert config.timeout_seconds is None
        assert config.role == "primary"
        assert config.temperature_strategy == TemperatureStrategy.FIXED

    def test_with_overrides(self):
        config = PhaseConfig()
        new_config = config.with_overrides(temperature=0.5, max_tokens=1024)
        assert new_config.temperature == 0.5
        assert new_config.max_tokens == 1024
        # Original unchanged
        assert config.temperature == 1.0

    def test_frozen_prevents_mutation(self):
        config = PhaseConfig()
        with pytest.raises(AttributeError):
            config.temperature = 0.5

    def test_temperature_strategy_values(self):
        assert TemperatureStrategy.FIXED.value == "fixed"
        assert TemperatureStrategy.ESCALATE.value == "escalate"
        assert TemperatureStrategy.DEESCALATE.value == "deescalate"
        assert TemperatureStrategy.SWEEP.value == "sweep"


class TestPhaseResult:
    """Test PhaseResult dataclass."""

    def test_succeeded_when_output_present_no_errors(self):
        result = PhaseResult(
            phase_name="test",
            output={"key": "value"},
            tokens={"input": 10, "output": 20},
            model_used="test-model",
            duration_seconds=1.0,
        )
        assert result.succeeded is True

    def test_failed_when_output_none(self):
        result = PhaseResult(
            phase_name="test",
            output=None,
            tokens={"input": 10, "output": 0},
            model_used="test-model",
            duration_seconds=1.0,
            errors=["Something went wrong"],
        )
        assert result.succeeded is False

    def test_failed_when_errors_present(self):
        result = PhaseResult(
            phase_name="test",
            output={"key": "value"},
            tokens={"input": 10, "output": 20},
            model_used="test-model",
            duration_seconds=1.0,
            errors=["Parse error"],
        )
        assert result.succeeded is False

    def test_frozen_prevents_mutation(self):
        result = PhaseResult(
            phase_name="test",
            output={},
            tokens={},
            model_used="m",
            duration_seconds=1.0,
        )
        with pytest.raises(AttributeError):
            result.phase_name = "other"


class TestMakePhaseResult:
    """Test convenience constructor."""

    def test_computes_duration(self):
        start = time.monotonic()
        time.sleep(0.05)
        result = make_phase_result(
            phase_name="test",
            output={},
            tokens={"input": 10, "output": 20},
            model_used="test-model",
            start_time=start,
        )
        assert result.duration_seconds >= 0.0  # just ensure it's non-negative
        assert result.phase_name == "test"
        assert result.errors == []

    def test_accepts_errors(self):
        result = make_phase_result(
            phase_name="test",
            output=None,
            tokens={},
            model_used="m",
            start_time=time.monotonic(),
            errors=["fail"],
        )
        assert result.errors == ["fail"]
        assert result.succeeded is False
