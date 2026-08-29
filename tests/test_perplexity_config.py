"""Regression tests for provider configuration."""

from reasoner.llm import _REGISTRY, _json_response_format


def test_perplexity_registry_defaults_match_intended_search_profiles():
    # sonar-pro / sonar-reasoning-pro / sonar-deep-research were deliberately
    # bumped to "high" context / reasoning effort for quality — only the base
    # "sonar" tier stays "low".
    assert _REGISTRY["sonar"]["extra_body"]["web_search_options"]["search_context_size"] == "low"
    assert _REGISTRY["sonar-pro"]["extra_body"]["web_search_options"]["search_context_size"] == "high"
    assert _REGISTRY["sonar-reasoning-pro"]["extra_body"]["web_search_options"]["search_context_size"] == "high"
    assert _REGISTRY["sonar-deep-research"]["extra_body"]["reasoning_effort"] == "high"


def test_structured_outputs_only_enable_for_strict_json_non_hybrid_perplexity_calls():
    # Providers carry the fully-qualified served model string as `self.model`
    # (registry.build_provider's "openrouter" branch passes cfg["model"]
    # straight through) — that is the shape _json_response_format actually
    # sees in production, so these tests exercise that shape rather than the
    # bare "sonar-pro"-style alias.
    strict_json = _json_response_format(
        "perplexity/sonar-pro",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"task_type": "..."}',
    )
    assert strict_json is not None
    assert strict_json["type"] == "json_object"

    hybrid = _json_response_format(
        "perplexity/sonar-pro",
        "You are a synthesizer.",
        "[SOLUTION]\nWrite prose here.\n[/SOLUTION]",
    )
    assert hybrid is None

    reasoning = _json_response_format(
        "perplexity/sonar-reasoning-pro",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"task_type": "..."}',
    )
    assert reasoning is None

    deep_research = _json_response_format(
        "perplexity/sonar-deep-research",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"perspective": "constructive"}',
    )
    assert deep_research is None


def test_structured_outputs_extend_to_any_model_the_capability_registry_says_supports_it():
    # The generalisation this replaces a Perplexity-only hardcode with: a
    # non-Perplexity model that advertises response_format/structured_outputs
    # in the OpenRouter catalogue now gets JSON mode too. This is the actual
    # bug from docs/plans/article-flow-truncation-remediation.md — qwen3.5-flash
    # answered a JSON-contract prompt with chain-of-thought prose instead of
    # JSON, and nothing was asking it to use the mode it advertised.
    result = _json_response_format(
        "qwen/qwen3.5-flash-02-23",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"argument_map": {}}',
    )
    assert result is not None
    assert result["type"] == "json_object"


def test_structured_outputs_withheld_for_unprofiled_model():
    result = _json_response_format(
        "some-vendor/unknown-model-id",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"task_type": "..."}',
    )
    assert result is None


def test_google_registry_uses_current_stable_gemini_model_ids():
    # "claude-sonnet" is a deliberate cross-vendor alias to claude-sonnet-5
    # (v3.4) and "gemini-flash" doesn't exist as a key (dedup fix, see
    # registry.py comment above the Google block) — real Google IDs live
    # under "gemini-pro-real" / "gemini-2.5-flash".
    assert _REGISTRY["gemini-pro-real"]["model"] == "google/gemini-3.1-pro-preview"
    assert _REGISTRY["gemini-2.5-flash"]["model"] == "google/gemini-2.5-flash"
