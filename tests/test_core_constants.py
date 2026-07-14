"""Tests for core constants and configuration defaults."""

from __future__ import annotations

import pytest

from reasoner.core import constants as const


class TestTokenBudgets:
    """Verify token budget constants are reasonable."""

    def test_phase_budgets_are_positive(self):
        for phase, budget in const.PHASE_TOKEN_BUDGETS.items():
            assert budget > 0, f"Phase {phase} has non-positive budget {budget}"

    def test_default_budget_positive(self):
        assert const.PHASE_TOKEN_BUDGETS["default"] > 0

    def test_default_max_tokens_positive(self):
        assert const.DEFAULT_MAX_TOKENS > 0

    def test_truncation_limits_positive(self):
        assert const.TRUNCATION.PROBLEM > 0
        assert const.TRUNCATION.CONTENT > 0
        assert const.TRUNCATION.SOLUTION > 0

    def test_get_token_budget_fallback(self):
        assert const.get_token_budget("nonexistent_phase") == const.PHASE_TOKEN_BUDGETS["default"]


class TestTimeoutDefaults:
    """Verify timeout constants."""

    def test_timeouts_positive(self):
        assert const.TIMEOUTS.HEALTH_CHECK > 0
        assert const.TIMEOUTS.LLM_CALL > 0
        assert const.TIMEOUTS.SEARCH_CLIENT > 0

    def test_phase_timeouts_positive(self):
        for phase, timeout in const.PHASE_TIMEOUTS.items():
            assert timeout > 0, f"Phase {phase} has non-positive timeout {timeout}"

    def test_get_phase_timeout_fallback(self):
        assert const.get_phase_timeout("nonexistent_phase") == const.PHASE_TIMEOUTS["default"]


class TestTopKDefaults:
    """Verify top-k configuration."""

    def test_default_top_k_positive(self):
        assert const.DEFAULT_TOP_K > 0


class TestCORSConfig:
    """Verify CORS configuration."""

    def test_cors_max_age_positive(self):
        assert const.CORS_MAX_AGE_SECONDS > 0


class TestRetryBudgets:
    """Verify phase retry budgets."""

    def test_retry_budgets_positive(self):
        for phase, budget in const.PHASE_RETRY_BUDGETS.items():
            assert budget >= 0, f"Phase {phase} has negative retry budget {budget}"

    def test_get_phase_retry_budget_fallback(self):
        assert const.get_phase_retry_budget("nonexistent_phase") == const.PHASE_RETRY_BUDGETS["default"]


class TestQualityJudgeConfig:
    """Verify quality judge configuration."""

    def test_quality_judge_models_defined(self):
        assert "budget" in const.QUALITY_JUDGE_MODELS
        assert "premium" in const.QUALITY_JUDGE_MODELS

    def test_quality_judge_thresholds_reasonable(self):
        assert const.QUALITY_JUDGE_THRESHOLDS["budget"] > 0
        assert const.QUALITY_JUDGE_THRESHOLDS["premium"] > const.QUALITY_JUDGE_THRESHOLDS["budget"]

    def test_get_quality_judge_model_premium(self):
        model = const.get_quality_judge_model("some-premium-preset")
        assert model == const.QUALITY_JUDGE_MODELS["premium"]

    def test_get_quality_judge_model_budget(self):
        model = const.get_quality_judge_model("some-budget-preset")
        assert model == const.QUALITY_JUDGE_MODELS["budget"]

    def test_get_quality_judge_threshold_premium(self):
        threshold = const.get_quality_judge_threshold("some-premium-preset")
        assert threshold == const.QUALITY_JUDGE_THRESHOLDS["premium"]


class TestBaseUrls:
    """Verify base URLs are well-formed."""

    def test_searxng_url_is_http(self):
        assert const.DEFAULT_SEARXNG_URL.startswith("http")

    def test_openrouter_url_is_https(self):
        assert const.OPENROUTER_BASE_URL.startswith("https")

    def test_openai_url_is_https(self):
        assert const.OPENAI_BASE_URL.startswith("https")


class TestModelAliases:
    """Verify model aliases are non-empty strings."""

    def test_claude_alias(self):
        assert isinstance(const.MODEL_CLAUDE_SONNET, str)
        assert len(const.MODEL_CLAUDE_SONNET) > 0

    def test_gemini_flash_alias(self):
        assert isinstance(const.MODEL_GEMINI_FLASH, str)
        assert len(const.MODEL_GEMINI_FLASH) > 0
