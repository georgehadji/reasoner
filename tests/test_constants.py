"""
Regression tests for centralized constants and settings.

Ensures that:
- All token budgets are positive
- All timeouts are positive floats
- Base URLs are valid strings
- Defaults exist in PRESETS
- get_method_from_preset returns expected values
"""

import pytest
from reasoner.core.constants import (
    PHASE_TOKEN_BUDGETS,
    TIMEOUTS,
    TRUNCATION,
    DEFAULT_NEURO_URL,
    DEFAULT_OLLAMA_URL,
    OPENROUTER_BASE_URL,
    OPENAI_BASE_URL,
    ANTHROPIC_BASE_URL,
    GOOGLE_BASE_URL,
    DEFAULT_PRESET,
    DEFAULT_CLI_PRESET,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_SEQUENTIAL,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_NUM_SUGGESTIONS,
    DEFAULT_SEARCH_RESULTS,
    DEFAULT_MAX_DECOMPOSED_QUERIES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_DELAY,
    CORS_MAX_AGE_SECONDS,
    MAX_CACHE_FILES,
    MAX_CIRCUIT_BREAKER_REGISTRY_SIZE,
    MAX_RATE_LIMIT_BUCKETS,
    get_token_budget,
)
from reasoner.presets import PRESETS, get_method_from_preset


class TestConstants:
    def test_phase_token_budgets_are_positive(self):
        for role, budget in PHASE_TOKEN_BUDGETS.items():
            assert budget > 0, f"Budget for {role} must be positive, got {budget}"

    def test_timeouts_are_positive_floats(self):
        for name, value in TIMEOUTS.__dict__.items():
            if not name.startswith("_"):
                assert isinstance(value, float), f"TIMEOUTS.{name} must be a float"
                assert value > 0, f"TIMEOUTS.{name} must be positive"

    def test_truncation_limits_are_positive_ints(self):
        for name, value in TRUNCATION.__dict__.items():
            if not name.startswith("_"):
                assert isinstance(value, int), f"TRUNCATION.{name} must be an int"
                assert value >= 0, f"TRUNCATION.{name} must be non-negative"

    def test_base_urls_are_valid_strings(self):
        urls = [
            DEFAULT_NEURO_URL,
            DEFAULT_OLLAMA_URL,
            OPENROUTER_BASE_URL,
            OPENAI_BASE_URL,
            ANTHROPIC_BASE_URL,
            GOOGLE_BASE_URL,
        ]
        for url in urls:
            assert isinstance(url, str)
            assert url.startswith("http")

    def test_default_presets_exist(self):
        assert DEFAULT_PRESET in PRESETS, f"DEFAULT_PRESET '{DEFAULT_PRESET}' not found in PRESETS"
        assert DEFAULT_CLI_PRESET in PRESETS, f"DEFAULT_CLI_PRESET '{DEFAULT_CLI_PRESET}' not found in PRESETS"

    def test_simple_constants_are_sensible(self):
        assert DEFAULT_MAX_TOKENS > 0
        assert 0.0 <= DEFAULT_TEMPERATURE <= 2.0
        assert DEFAULT_TOP_K > 0
        assert isinstance(DEFAULT_SEQUENTIAL, bool)
        assert DEFAULT_SOURCE_TYPE in ("general", "academic", "social", "news", "code")
        assert DEFAULT_NUM_SUGGESTIONS > 0
        assert DEFAULT_SEARCH_RESULTS > 0
        assert DEFAULT_MAX_DECOMPOSED_QUERIES > 0
        assert DEFAULT_MAX_RETRIES >= 0
        assert DEFAULT_BACKOFF_BASE > 0
        assert DEFAULT_BACKOFF_DELAY >= 0.0
        assert CORS_MAX_AGE_SECONDS > 0
        assert MAX_CACHE_FILES > 0
        assert MAX_CIRCUIT_BREAKER_REGISTRY_SIZE > 0
        assert MAX_RATE_LIMIT_BUCKETS > 0

    def test_get_token_budget_fallback(self):
        assert get_token_budget("fusion") == PHASE_TOKEN_BUDGETS["fusion"]
        assert get_token_budget("nonexistent_role") == PHASE_TOKEN_BUDGETS["default"]


class TestGetMethodFromPreset:
    @pytest.mark.parametrize(
        "preset,expected",
        [
            ("debate-budget", "debate"),
            ("jury-budget", "jury"),
            ("orchestrated-premium", "jury"),
            ("research-budget", "research"),
            ("scientific-premium", "scientific"),
            ("socratic-budget", "socratic"),
            ("multi-perspective-budget", "multi-perspective"),
            ("claude-only", "multi-perspective"),
            ("", "multi-perspective"),
        ],
    )
    def test_mapping(self, preset, expected):
        assert get_method_from_preset(preset) == expected
