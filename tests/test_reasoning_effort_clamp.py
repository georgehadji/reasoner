"""Reasoning-effort clamping against per-model ``supported_efforts``.

Guards the bug these tests were written for: the per-phase effort in
``core.temperatures.PHASE_REASONING_EFFORT`` is chosen before routing, so it was
being sent verbatim to models that do not accept it — "minimal" (classification,
fusion) is unsupported on most reasoning models.
"""

from __future__ import annotations

import pytest

from reasoner.core.temperatures import PHASE_REASONING_EFFORT
from reasoner.infrastructure.llm.reasoning_effort import (
    EFFORT_LADDER,
    clamp_effort,
    clamp_extra_body,
    supported_efforts,
)


class TestClampEffort:
    def test_supported_effort_passes_through(self):
        assert clamp_effort("high", ("high", "medium", "low")) == "high"

    def test_minimal_clamps_to_nearest_supported(self):
        # The real gemini-3.8-flash case: classification asks "minimal".
        assert clamp_effort("minimal", ("high", "medium", "low")) == "low"

    def test_clamps_upward_when_only_stronger_levels_exist(self):
        # deepseek-v4-pro advertises only xhigh|high.
        assert clamp_effort("low", ("xhigh", "high")) == "high"

    def test_tie_breaks_toward_less_thinking(self):
        # "medium" is equidistant from "high" and "low"; prefer the cheaper side
        # so a downgrade never silently becomes an upgrade.
        assert clamp_effort("medium", ("high", "low")) == "low"

    def test_never_substitutes_none_for_a_thinking_phase(self):
        # Disabling reasoning is a behaviour change, not a clamp.
        assert clamp_effort("minimal", ("none", "high")) == "high"

    def test_none_is_honoured_when_explicitly_requested(self):
        assert clamp_effort("none", ("none", "high")) == "none"

    def test_unknown_desired_level_is_left_alone(self):
        assert clamp_effort("bogus", ("high", "low")) == "bogus"

    @pytest.mark.parametrize("phase,effort", sorted(PHASE_REASONING_EFFORT.items()))
    def test_every_configured_phase_effort_is_on_the_ladder(self, phase, effort):
        assert effort in EFFORT_LADDER, f"{phase} configures unknown effort {effort!r}"


class TestSupportedEfforts:
    def test_unknown_model_is_unconstrained(self):
        assert supported_efforts("not-a-real-model/nope") is None

    def test_restricted_model_reports_its_list(self):
        # Read from the bundled catalogue snapshot; skip if this model is not in
        # the current refresh rather than pinning the test to a live vendor.
        efforts = supported_efforts("google/gemini-3.8-flash")
        if efforts is None:
            pytest.skip("google/gemini-3.8-flash absent from catalogue snapshot")
        assert "minimal" not in efforts
        assert set(efforts) <= set(EFFORT_LADDER)


class TestClampExtraBody:
    def test_passthrough_without_reasoning_key(self):
        body = {"usage": {"include": True}}
        assert clamp_extra_body("google/gemini-3.8-flash", body) is body

    def test_passthrough_for_unconstrained_model(self):
        body = {"reasoning": {"effort": "minimal"}}
        assert clamp_extra_body("not-a-real-model/nope", body) is body

    def test_does_not_mutate_the_original(self):
        body = {"reasoning": {"effort": "minimal"}, "usage": {"include": True}}
        out = clamp_extra_body("google/gemini-3.8-flash", body)
        if out is body:
            pytest.skip("google/gemini-3.8-flash absent from catalogue snapshot")
        assert body["reasoning"]["effort"] == "minimal", "input was mutated"
        assert out["reasoning"]["effort"] == "low"
        assert out["usage"] == {"include": True}, "sibling keys must survive"

    def test_none_and_empty_are_safe(self):
        assert clamp_extra_body("google/gemini-3.8-flash", None) is None
        assert clamp_extra_body("google/gemini-3.8-flash", {}) == {}
