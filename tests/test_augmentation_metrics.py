"""
Unit tests for augmentation A/B quality metrics service.

Tests deterministic arm assignment, metric payload structure,
and the environment-togglable baseline disabling.
"""

from __future__ import annotations

from reasoner.application.services.augmentation_metrics import (
    assign_ab_arm,
    build_ab_metric,
    should_disable_augmentation_for_ab,
)


class TestABArmAssignment:
    """Deterministic 50/50 split must be reproducible."""

    def test_same_input_yields_same_arm(self):
        """Same problem + same run_id → same arm every time."""
        arm1 = assign_ab_arm("What is art?", "run-abc-123")
        arm2 = assign_ab_arm("What is art?", "run-abc-123")
        assert arm1 == arm2

    def test_different_input_yields_different_arm(self):
        """Different problem or run_id may assign different arm (probabilistic)."""
        arms = {
            assign_ab_arm("What is art?", f"run-{i}") for i in range(20)
        }
        # With 20 different run_ids, we should see both arms (highly likely)
        assert len(arms) == 2, "Should observe both augmented and baseline arms"

    def test_arm_is_always_augmented_or_baseline(self):
        """Arm must be one of the two valid values."""
        for i in range(50):
            arm = assign_ab_arm(f"question-{i}", f"run-{i}")
            assert arm in ("augmented", "baseline"), f"Unexpected arm: {arm}"

    def test_problem_hash_in_metric_is_consistent(self):
        """Same problem produces same hash in metric payload."""
        metric1 = build_ab_metric("augmented", "What is art?", "r1", "article-budget", {})
        metric2 = build_ab_metric("augmented", "What is art?", "r1", "article-budget", {})
        assert metric1["problem_hash"] == metric2["problem_hash"]


class TestABMetricPayload:
    """Metric payload must contain all required keys."""

    REQUIRED_TOP_KEYS = {"experiment", "arm", "problem_hash", "run_id", "preset", "metrics"}
    REQUIRED_METRIC_KEYS = {"article_length_chars", "source_count", "claim_count", "phase_count", "total_cost_usd"}

    def test_metric_has_all_top_level_keys(self):
        metric = build_ab_metric("augmented", "test", "r1", "preset", {})
        assert self.REQUIRED_TOP_KEYS.issubset(metric.keys()), (
            f"Missing keys: {self.REQUIRED_TOP_KEYS - set(metric.keys())}"
        )

    def test_metric_has_all_sub_metric_keys(self):
        metric = build_ab_metric("augmented", "test", "r1", "preset", {})
        assert self.REQUIRED_METRIC_KEYS.issubset(metric["metrics"].keys()), (
            f"Missing metric keys: {self.REQUIRED_METRIC_KEYS - set(metric['metrics'].keys())}"
        )

    def test_metric_experiment_label_is_correct(self):
        metric = build_ab_metric("augmented", "test", "r1", "preset", {})
        assert metric["experiment"] == "augmentation_ab_v1"

    def test_metric_defaults_to_zero(self):
        """Missing state_summary keys should default to zero, not crash."""
        metric = build_ab_metric("augmented", "test", "r1", "preset", {})
        assert metric["metrics"]["article_length_chars"] == 0


class TestABShouldDisable:
    """should_disable_augmentation_for_ab respects the env toggle."""

    def test_disabled_when_ab_test_off(self):
        """When AUGMENTATION_AB_TEST is not set, should never disable."""
        # Default is false — never disable
        import os
        if "AUGMENTATION_AB_TEST" in os.environ:
            old = os.environ.pop("AUGMENTATION_AB_TEST")
            try:
                result = should_disable_augmentation_for_ab("test", "run-1")
                assert result is False
            finally:
                os.environ["AUGMENTATION_AB_TEST"] = old
        else:
            result = should_disable_augmentation_for_ab("test", "run-1")
            assert result is False
