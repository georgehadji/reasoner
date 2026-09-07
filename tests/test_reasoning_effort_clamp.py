"""Reasoning-effort clamping against per-model ``supported_efforts``.

Guards the bug these tests were written for: the per-phase effort in
``core.temperatures.PHASE_REASONING_EFFORT`` is chosen before routing, so it was
being sent verbatim to models that do not accept it — "minimal" (classification,
fusion) is unsupported on most reasoning models.
"""

from __future__ import annotations

import pytest

from reasoner.core.temperatures import PHASE_REASONING_EFFORT
from reasoner.domain.pricing import MODEL_CATALOGUE
from reasoner.infrastructure.llm.reasoning_effort import (
    EFFORT_LADDER,
    floor_max_tokens,
    reasoning_is_mandatory,
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


class TestFloorMaxTokens:
    """Budget headroom for models that always spend output tokens on reasoning.

    The bug: reasoning tokens are billed as output tokens and taken first, so a
    ``max_tokens`` sized for the visible reply alone yields an empty one — with
    HTTP 200 and a bill. ``openai/gpt-5`` is the primary of five premium
    presets and so serves their classification role at a 256-token budget;
    that combination produced 10 real e2e failures reported as
    ``Empty response ... for role=classification``.
    """

    def test_mandatory_reasoning_model_gets_headroom(self):
        assert floor_max_tokens("openai/gpt-5", 256, "minimal") > 256

    def test_higher_effort_demands_more_headroom(self):
        low = floor_max_tokens("openai/gpt-5", 256, "low")
        high = floor_max_tokens("openai/gpt-5", 256, "high")
        assert high > low, "an 80% reasoning cut needs a bigger budget than a 20% one"

    def test_a_generous_budget_is_left_alone(self):
        assert floor_max_tokens("openai/gpt-5", 100_000, "high") == 100_000

    def test_never_lowers_the_callers_budget(self):
        for effort in EFFORT_LADDER:
            assert floor_max_tokens("openai/gpt-5", 4096, effort) >= 4096

    def test_default_enabled_alone_does_not_trigger_a_raise(self):
        """anthropic/claude-sonnet-5 advertises default_enabled but reports
        reasoning_tokens: 0 on a live call. It is the primary of 19 presets, so
        keying on default_enabled would inflate most traffic in the system."""
        if not MODEL_CATALOGUE.get("anthropic/claude-sonnet-5"):
            pytest.skip("anthropic/claude-sonnet-5 absent from catalogue snapshot")
        assert not reasoning_is_mandatory("anthropic/claude-sonnet-5")
        assert floor_max_tokens("anthropic/claude-sonnet-5", 256, None) == 256

    def test_unknown_model_is_untouched(self):
        assert floor_max_tokens("not-a-real-model/nope", 256, "high") == 256

    def test_nonpositive_budget_is_untouched(self):
        assert floor_max_tokens("openai/gpt-5", 0, "high") == 0

    def test_missing_effort_falls_back_to_the_model_default(self):
        """The provider may send no explicit effort; the model still reasons."""
        assert floor_max_tokens("openai/gpt-5", 256, None) > 256
