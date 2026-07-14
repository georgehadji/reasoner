"""Tests for TemperatureStrategy and retry-aware temperature resolution."""

from __future__ import annotations

import pytest

from reasoner.core.protocol import PhaseConfig, TemperatureStrategy
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.models import PipelineState


class TestTemperatureStrategyEnum:
    """Basic enum behaviour."""

    def test_members(self):
        assert TemperatureStrategy.FIXED.value == "fixed"
        assert TemperatureStrategy.ESCALATE.value == "escalate"
        assert TemperatureStrategy.DEESCALATE.value == "deescalate"
        assert TemperatureStrategy.SWEEP.value == "sweep"


class TestPhaseConfigWithStrategy:
    """PhaseConfig dataclass integration."""

    def test_default_strategy_is_fixed(self):
        cfg = PhaseConfig(temperature=0.5)
        assert cfg.temperature_strategy == TemperatureStrategy.FIXED

    def test_with_overrides_preserves_strategy(self):
        cfg = PhaseConfig(temperature=0.5, temperature_strategy=TemperatureStrategy.ESCALATE)
        overridden = cfg.with_overrides(max_tokens=100)
        assert overridden.temperature_strategy == TemperatureStrategy.ESCALATE

    def test_override_strategy(self):
        cfg = PhaseConfig(temperature=0.5, temperature_strategy=TemperatureStrategy.FIXED)
        overridden = cfg.with_overrides(temperature_strategy=TemperatureStrategy.SWEEP)
        assert overridden.temperature_strategy == TemperatureStrategy.SWEEP


class TestTemperatureResolution:
    """Temperature resolution inside LLMExecutor.execute()."""

    @pytest.fixture
    def dummy_state(self):
        return PipelineState(problem="test")

    @pytest.fixture
    def executor(self, dummy_state):
        # Minimal executor with a fake router
        class FakeRouter:
            def get(self, role):
                return type("P", (), {"model": "gpt-4o"})()

            async def call(self, **kwargs):
                raise NotImplementedError("should be monkeypatched")

            cascading_routing = {}

        return LLMExecutor(
            router=FakeRouter(),
            phase_configs={
                "creative": PhaseConfig(
                    temperature=0.7,
                    temperature_strategy=TemperatureStrategy.ESCALATE,
                ),
                "structured": PhaseConfig(
                    temperature=0.4,
                    temperature_strategy=TemperatureStrategy.DEESCALATE,
                ),
                "sweep_role": PhaseConfig(
                    temperature=0.5,
                    temperature_strategy=TemperatureStrategy.SWEEP,
                ),
                "fixed_role": PhaseConfig(
                    temperature=0.5,
                    temperature_strategy=TemperatureStrategy.FIXED,
                ),
            },
            token_cache=None,
            caching_enabled=False,
        )

    @pytest.mark.asyncio
    async def test_fixed_temperature_no_retry(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        await executor.execute("fixed_role", "sys", "user", dummy_state, _retry_attempt=0)
        assert calls[-1] == 0.5

    @pytest.mark.asyncio
    async def test_escalate_increases_temperature(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        await executor.execute("creative", "sys", "user", dummy_state, _retry_attempt=2)
        # base 0.7 + 0.1*2 = 0.9
        assert calls[-1] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_escalate_caps_at_1_0(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        await executor.execute("creative", "sys", "user", dummy_state, _retry_attempt=10)
        assert calls[-1] == 1.0

    @pytest.mark.asyncio
    async def test_deescalate_decreases_temperature(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        await executor.execute("structured", "sys", "user", dummy_state, _retry_attempt=2)
        # base 0.4 - 0.05*2 = 0.3
        assert calls[-1] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_deescalate_floors_at_0_0(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        await executor.execute("structured", "sys", "user", dummy_state, _retry_attempt=20)
        assert calls[-1] == 0.0

    @pytest.mark.asyncio
    async def test_sweep_cycles_values(self, executor, dummy_state, monkeypatch):
        calls = []

        async def fake_call(*args, **kwargs):
            calls.append(kwargs.get("temperature"))
            return "ok", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(executor.router, "call", fake_call)
        for attempt, expected in enumerate([0.1, 0.5, 0.9, 0.9]):
            await executor.execute("sweep_role", "sys", "user", dummy_state, _retry_attempt=attempt)
            assert calls[-1] == expected
