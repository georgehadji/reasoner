"""Tests for temperature configuration."""

from __future__ import annotations

from reasoner.core.temperatures import NON_PHASE_TEMPERATURES, PHASE_TEMPERATURES


class TestPhaseTemperatures:
    """Verify phase temperature values are within valid ranges."""

    def test_all_temperatures_in_valid_range(self):
        for phase, temp in PHASE_TEMPERATURES.items():
            assert 0.0 <= temp <= 2.0, f"Phase {phase} temperature {temp} out of range"

    def test_structured_phases_have_low_temperature(self):
        assert PHASE_TEMPERATURES["classification"] <= 0.5
        assert PHASE_TEMPERATURES["scoring"] <= 0.5
        assert PHASE_TEMPERATURES["verifier"] <= 0.5

    def test_creative_phases_have_high_temperature(self):
        assert PHASE_TEMPERATURES["perspective"] >= 0.7
        assert PHASE_TEMPERATURES["generator"] >= 0.5

    def test_critic_has_lowest_temperature(self):
        assert PHASE_TEMPERATURES["critic"] <= PHASE_TEMPERATURES["classification"]

    def test_non_phase_temperatures_in_range(self):
        for context, temp in NON_PHASE_TEMPERATURES.items():
            assert 0.0 <= temp <= 2.0, f"Context {context} temperature {temp} out of range"

    def test_fallback_temperature_exists(self):
        assert "primary" in PHASE_TEMPERATURES
