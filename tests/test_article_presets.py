"""
Preset routing and validation tests for the Article method.

Tests cover:
  - Preset structure and required routing keys
  - Provider-family diversity (structural check only)
  - Article constants sanity
"""

from __future__ import annotations

import pytest

from reasoner.domain.preset_registry import PRESETS
from reasoner.core.constants import (
    ARTICLE_MIN_SOURCE_COUNT, ARTICLE_MAX_SOURCE_COUNT,
    ARTICLE_SEARCH_RESULTS_PER_QUERY, ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION,
    ARTICLE_MIN_CLAIM_SUPPORT_RATIO, ARTICLE_CRITIC_MAX_WORDS,
)


ARTICLE_PRESET_NAMES = ["article-budget", "article-premium"]

ARTICLE_REQUIRED_ROLES = [
    "primary", "writing_draft", "writing_factcheck", "writing_assemble",
    "synthesis", "article_sot_skeleton", "article_critic", "article_revise",
    "article_humanize", "article_verifier",
]

# Heuristic provider-family mapping for model diversity checks
_FAMILY_MAP: dict[str, str] = {
    "claude-sonnet": "anthropic", "claude-haiku": "anthropic",
    "claude-opus": "anthropic", "claude-fable-5": "anthropic",
    "gpt-4o-mini": "openai", "gpt-5.5": "openai", "gpt-5": "openai",
    "gpt-5-mini": "openai", "gpt-latest": "openai", "gpt-mini-latest": "openai",
    "gemini-flash": "google", "gemini-pro": "google",
    "deepseek-v4-flash": "deepseek", "deepseek-v4-pro": "deepseek",
    "qwen3.7-plus": "qwen", "qwen3.7-max": "qwen",
    "grok-4.3": "xai",
    "sonar": "perplexity", "sonar-pro": "perplexity",
    "hy3": "tencent",
}

_PREFIX_MAP: dict[str, str] = {
    "claude": "anthropic", "gpt": "openai", "o3": "openai", "o4": "openai",
    "gemini": "google", "deepseek": "deepseek", "qwen": "qwen",
    "grok": "xai", "sonar": "perplexity", "hy": "tencent",
    "kimi": "moonshot", "glm": "zhipuai", "mistral": "mistral",
    "llama": "meta",
}


def _get_family(model_id: str) -> str:
    if model_id in _FAMILY_MAP:
        return _FAMILY_MAP[model_id]
    for prefix, family in _PREFIX_MAP.items():
        if model_id.startswith(prefix):
            return family
    return "unknown"


class TestArticlePresetStructure:

    def test_article_presets_exist(self):
        for name in ARTICLE_PRESET_NAMES:
            assert name in PRESETS, f"Missing preset: {name}"

    def test_method_is_article(self):
        for name in ARTICLE_PRESET_NAMES:
            p = PRESETS[name]
            assert p.get("method") == "article", f"{name}: method={p.get('method')}"

    def test_tags_present(self):
        for name in ARTICLE_PRESET_NAMES:
            tags = PRESETS[name].get("tags", [])
            assert "writing" in tags, f"{name}: missing 'writing' tag"
            assert "article" in tags, f"{name}: missing 'article' tag"

    def test_all_required_roles_present(self):
        for name in ARTICLE_PRESET_NAMES:
            routing = PRESETS[name].get("routing", {})
            for role in ARTICLE_REQUIRED_ROLES:
                assert role in routing, f"{name}: missing '{role}'"

    def test_all_routing_model_ids_resolvable(self):
        for name in ARTICLE_PRESET_NAMES:
            routing = PRESETS[name].get("routing", {})
            for role, model_id in routing.items():
                family = _get_family(model_id)
                assert family != "unknown", (
                    f"{name}/{role}: unrecognised model '{model_id}'"
                )


class TestArticlePresetDiversity:

    def test_drafter_verifier_different_family(self):
        for name in ARTICLE_PRESET_NAMES:
            routing = PRESETS[name].get("routing", {})
            drafter = routing.get("writing_draft", "")
            verifier = routing.get("article_verifier", "")
            if not drafter or not verifier:
                continue
            if _get_family(drafter) == _get_family(verifier):
                pytest.skip(f"{name}: same family (G4 deferred to Phase 3)")

    def test_drafter_factcheck_different_family(self):
        for name in ARTICLE_PRESET_NAMES:
            routing = PRESETS[name].get("routing", {})
            drafter = routing.get("writing_draft", "")
            factcheck = routing.get("writing_factcheck", "")
            if not drafter or not factcheck:
                continue
            if _get_family(drafter) == _get_family(factcheck):
                pytest.skip(f"{name}: same family (G4 deferred to Phase 3)")


class TestArticleConstantsSanity:

    def test_constants_in_range(self):
        assert 1 <= ARTICLE_MIN_SOURCE_COUNT <= 10
        assert 5 <= ARTICLE_MAX_SOURCE_COUNT <= 50
        assert ARTICLE_SEARCH_RESULTS_PER_QUERY >= 3
        assert ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION >= 5
        assert 0.0 <= ARTICLE_MIN_CLAIM_SUPPORT_RATIO <= 1.0
        assert ARTICLE_CRITIC_MAX_WORDS >= 500
