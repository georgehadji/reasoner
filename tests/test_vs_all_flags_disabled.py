"""Golden regression — VS code paths behave correctly when all flags disabled."""
from __future__ import annotations

from reasoner.vs_config import VSFeatureFlags, VSVerticalConfig, VSVerticalRegistry
from reasoner.reasoner_verbalized_sampling import (
    build_vs_prompt,
    VSMode,
    VSCandidate,
    VSResult,
    sample_from_vs,
    top_candidate,
)


class TestAllFlagsDisabledRegression:
    """Ensure primitives still function when feature flags are all disabled.

    Disabling flags must not change parsing, sampling, or prompt-building
    behavior — it only gates pipeline orchestration.
    """

    def test_all_disabled_flag_state(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        for value in flags.model_dump().values():
            assert value is False

    def test_prompt_building_unchanged_when_flags_disabled(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        # Prompt building is independent of feature flags
        system, user = build_vs_prompt("What is AI?", VSMode.STANDARD)
        assert "exactly" in system
        assert "What is AI?" in user
        assert flags.generation is False  # sanity: flags are off

    def test_parsing_and_sampling_unchanged_when_flags_disabled(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        raw = '{"candidates": [{"text": "answer", "probability": 1.0}]}'
        result = VSResult(candidates=[VSCandidate(text="answer", probability=1.0)], mode=VSMode.STANDARD)
        assert result.candidates[0].text == "answer"
        assert top_candidate(result.candidates).text == "answer"
        for _ in range(5):
            assert sample_from_vs(result.candidates).text == "answer"
        assert flags.probe_generation is False  # sanity: flags are off

    def test_registry_defaults_unchanged_when_flags_disabled(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        VSVerticalRegistry.clear()
        default = VSVerticalRegistry.get("nonexistent")
        assert default.domain == "default"
        assert default.k >= 2
        assert 0.0 < default.tail_threshold < 1.0
        assert flags.calibration is False  # sanity: flags are off
