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
    # in the OpenRouter catalogue now gets JSON mode too.
    #
    # This used to assert on qwen/qwen3.5-flash-02-23, named after the bug in
    # docs/plans/article-flow-truncation-remediation.md: that model answered a
    # JSON-contract prompt with chain-of-thought prose, and the conclusion was
    # that it simply had not been asked to use the mode it advertised. Measured
    # 2026-08-29, asking it does not help -- under json_object it collapses to a
    # bare scalar ("-1.0000000000000002e+308", "-1.025467398554854e+20") which
    # extract_json cannot parse at all, whereas with response_format omitted the
    # prose is merely a preamble and extract_json finds the object after it. It
    # is now in _JSON_MODE_DENYLIST, and the case below pins that.
    #
    # qwen3.7-flash keeps this test honest about what it is for: still a
    # non-Perplexity model, and verified to answer correctly both with and
    # without json_object.
    result = _json_response_format(
        "qwen/qwen3.7-flash",
        "Output ONLY valid JSON. No prose.",
        'Output JSON: {"argument_map": {}}',
    )
    assert result is not None
    assert result["type"] == "json_object"


def test_structured_outputs_withheld_for_models_that_collapse_under_json_mode():
    """Denylisted models must get no response_format, however capable the catalogue says they are.

    Both advertise structured-output support and both produce unparseable
    output when it is used: qwen3.5-flash a bare float, qwen3.6-flash an empty
    string. Omitting response_format is what makes them usable, so the denylist
    is load-bearing rather than a precaution.
    """
    for model in ("qwen/qwen3.5-flash-02-23", "qwen/qwen3.6-flash"):
        assert _json_response_format(
            model,
            "Output ONLY valid JSON. No prose.",
            'Output JSON: {"argument_map": {}}',
        ) is None, f"{model} is denylisted but was still handed a response_format"


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
