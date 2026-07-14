"""Regression tests for provider configuration."""

from reasoner.llm import _REGISTRY, _perplexity_response_format
from reasoner.presets import get_preset


def test_perplexity_registry_defaults_match_intended_search_profiles():
    assert _REGISTRY["sonar"]["extra_body"]["web_search_options"]["search_context_size"] == "low"
    assert _REGISTRY["sonar-pro"]["extra_body"]["web_search_options"]["search_context_size"] == "medium"
    assert _REGISTRY["sonar-reasoning-pro"]["extra_body"]["web_search_options"]["search_context_size"] == "medium"
    assert _REGISTRY["sonar-deep-research"]["extra_body"]["reasoning_effort"] == "low"


def test_structured_outputs_only_enable_for_strict_json_non_hybrid_perplexity_calls():
    strict_json = _perplexity_response_format(
        "sonar-pro",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"task_type": "..."}',
    )
    assert strict_json is not None
    assert strict_json["type"] == "json_schema"

    hybrid = _perplexity_response_format(
        "sonar-pro",
        "You are a synthesizer.",
        "[SOLUTION]\nWrite prose here.\n[/SOLUTION]",
    )
    assert hybrid is None

    reasoning = _perplexity_response_format(
        "sonar-reasoning-pro",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"task_type": "..."}',
    )
    assert reasoning is None

    deep_research = _perplexity_response_format(
        "sonar-deep-research",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"perspective": "constructive"}',
    )
    assert deep_research is None


def test_google_registry_uses_current_stable_gemini_model_ids():
    assert _REGISTRY["gemini-pro"]["model"] == "google/gemini-2.5-pro"
    assert _REGISTRY["gemini-flash"]["model"] == "google/gemini-2.5-flash"
