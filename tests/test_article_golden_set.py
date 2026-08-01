"""
Golden set regression tests for the Article pipeline (Phase 0).

20 frozen test inputs spanning all venues, each run through 9 prompt builders.
Baseline comparison via ARTICLE_CHECK_BASELINE env var.

Tests are purely structural — no LLM calls required.
"""

from __future__ import annotations

import json
import os

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import is_article_request, detect_language
import reasoner.phases.article as article_prompts
from reasoner.core.constants import (
    ARTICLE_MIN_SOURCE_COUNT, ARTICLE_MAX_SOURCE_COUNT,
    ARTICLE_SEARCH_RESULTS_PER_QUERY, ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION,
    ARTICLE_MIN_CLAIM_SUPPORT_RATIO, ARTICLE_CRITIC_MAX_WORDS, TRUNCATION,
)

# ── Golden set ───────────────────────────────────────────────────────────────

GOLDEN_SET = [
    # Blog posts
    {"id": "blog_climate", "problem": "Write a blog post about the economic impact of climate change on coastal communities in Southeast Asia", "expected_class": "blog", "language": "English"},
    {"id": "blog_remote_work", "problem": "Draft a blog post about the future of remote work and its effect on urban development", "expected_class": "blog", "language": "English"},
    # Explainer articles
    {"id": "explainer_quantum", "problem": "Write an explainer about quantum computing for a general audience", "expected_class": "explainer", "language": "English"},
    {"id": "explainer_mrna", "problem": "Draft an explainer article about how mRNA vaccines work", "expected_class": "explainer", "language": "English"},
    # Opinion / Op-Ed
    {"id": "oped_ai_regulation", "problem": "Write an opinion piece arguing that AI regulation should focus on capability audits", "expected_class": "op_ed", "language": "English"},
    {"id": "oped_education", "problem": "Draft an op-ed about why classical education still matters in the age of AI", "expected_class": "op_ed", "language": "English"},
    # Policy briefs
    {"id": "policy_eu_data", "problem": "Draft a policy brief analyzing the European Union approach to cross-border data flows", "expected_class": "policy_brief", "language": "English"},
    {"id": "policy_energy", "problem": "Write a policy analysis article comparing carbon pricing mechanisms across regions", "expected_class": "policy_brief", "language": "English"},
    # News analysis
    {"id": "news_semiconductor", "problem": "Write a news analysis article about the global semiconductor supply chain realignment", "expected_class": "news_analysis", "language": "English"},
    {"id": "news_cyber", "problem": "Compose a news analysis article about the shift in cybersecurity threats", "expected_class": "news_analysis", "language": "English"},
    # Technical articles
    {"id": "technical_llm", "problem": "Write a technical article explaining mixture-of-experts transformer models", "expected_class": "technical", "language": "English"},
    {"id": "technical_rust", "problem": "Draft a technical article about memory safety patterns in Rust", "expected_class": "technical", "language": "English"},
    # Greek briefing
    {"id": "greek_geopolitics", "problem": "\u0393\u03c1\u03ac\u03c8\u03c4\u03b5 \u03ad\u03bd\u03b1 \u03ac\u03c1\u03b8\u03c1\u03bf \u03b1\u03bd\u03ac\u03bb\u03c5\u03c3\u03b7\u03c2 \u03b3\u03b9\u03b1 \u03c4\u03b9\u03c2 \u03b3\u03b5\u03c9\u03c0\u03bf\u03bb\u03b9\u03c4\u03b9\u03ba\u03ad\u03c2 \u03b5\u03c0\u03b9\u03c0\u03c4\u03ce\u03c3\u03b5\u03b9\u03c2", "expected_class": "greek_briefing", "language": "Greek"},
    {"id": "greek_tech", "problem": "\u03a3\u03c5\u03bd\u03c4\u03ac\u03be\u03c4\u03b5 \u03ad\u03bd\u03b1 \u03ac\u03c1\u03b8\u03c1\u03bf \u03b3\u03b9\u03b1 \u03c4\u03b7\u03bd \u03b5\u03c0\u03af\u03b4\u03c1\u03b1\u03c3\u03b7 \u03c4\u03b7\u03c2 \u03c4\u03b5\u03c7\u03bd\u03b7\u03c4\u03ae\u03c2 \u03bd\u03bf\u03b7\u03bc\u03bf\u03c3\u03cd\u03bd\u03b7\u03c2", "expected_class": "greek_briefing", "language": "Greek"},
    # Styled articles
    {"id": "styled_newyorker", "problem": "Write an article about the decline of local news in rural America", "expected_class": "blog", "style_brief": {"author": "Jane Doe", "publication": "The New Yorker"}, "language": "English"},
    {"id": "styled_financial", "problem": "Draft an article analyzing the investment implications of deglobalization", "expected_class": "policy_brief", "style_brief": {"publication": "Financial Times"}, "language": "English"},
    # Deep questions
    {"id": "deep_consciousness", "problem": "Write an article exploring the philosophical debate about the nature of consciousness", "expected_class": "explainer", "expect_deep": True, "language": "English"},
    {"id": "deep_free_will", "problem": "Draft an article examining whether free will is compatible with modern neuroscience", "expected_class": "explainer", "expect_deep": True, "language": "English"},
    # Short review
    {"id": "short_review", "problem": "Write a short article reviewing Yuval Noah Harari's Nexus", "expected_class": "blog", "language": "English"},
    # Multi-source factual
    {"id": "factual_space", "problem": "Write an article about the Artemis program and its implications for international collaboration in space exploration", "expected_class": "news_analysis", "language": "English"},
]

IDS = [e["id"] for e in GOLDEN_SET]


def _build_state(entry: dict) -> PipelineState:
    """Build minimal PipelineState for prompt builder tests."""
    state = PipelineState(
        problem=entry["problem"],
        language=entry.get("language", "English"),
        preset_name="article-budget",
        method="article",
    )
    ws = state.writing_state
    ws["final_article"] = "# Draft\n\nBody text."
    ws["retrieved_sources"] = [{"title": f"S{i}", "url": f"https://x{i}.com", "snippet": f"snip{i}"} for i in range(5)]
    ws["source_metadata"] = ws["retrieved_sources"]
    ws["argument_map"] = {"central_question": "What?", "problem": "T", "current_explanations": ["A"], "limitations": ["B"], "new_insight": "C", "counterarguments": ["D"], "implications": ["E"]}
    ws["outline"] = [{"section_title": "Intro", "key_points": ["Hook"], "sources_used": [], "estimated_words": 200}]
    ws["suggested_title"] = "Test"
    ws["verification"] = {"verified_claims": [], "metrics": {"claim_support_ratio": 0.8}, "gaps": []}
    ws["claim_ledger"] = []
    ws["metrics"] = {"claim_support_ratio": 0.8}
    ws["structural_critique"] = {"overall_rigor_score": 0.7}
    ws["editorial_audit"] = {"passes_audit": True, "audit_score": 0.8}
    if entry.get("style_brief"):
        ws["style_brief"] = entry["style_brief"]
    return state


# ── Prompt builder parametrization ──────────────────────────────────────────

PROMPT_BUILDERS = [
    ("retrieval_plan", lambda s: article_prompts.article_retrieval_plan_prompt(s)),
    ("draft", lambda s: article_prompts.article_draft_prompt(s)),
    ("outline", lambda s: article_prompts.article_outline_prompt(s)),
    ("verify", lambda s: article_prompts.article_verify_prompt(s)),
    ("critic", lambda s: article_prompts.article_critic_prompt(s)),
    ("dev_edit", lambda s: article_prompts.article_developmental_edit_prompt(s)),
    ("style_edit", lambda s: article_prompts.article_style_edit_prompt(s)),
    ("copy_edit", lambda s: article_prompts.article_copy_edit_prompt(s)),
    ("final_audit", lambda s: article_prompts.article_final_audit_prompt(s)),
]

PROMPT_BUILDER_NAMES = [n for n, _ in PROMPT_BUILDERS]

# ── Baseline path ────────────────────────────────────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(HERE, "_data", "article_baseline.json")


# ══════════════════════════════════════════════════════════════════════════════
# Prompt builder structural tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenSetPromptLength:
    """Every prompt builder produces output for every golden-set entry."""

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=IDS)
    @pytest.mark.parametrize("pb_name,pb_fn", PROMPT_BUILDERS, ids=PROMPT_BUILDER_NAMES)
    def test_prompt_builds(self, entry: dict, pb_name: str, pb_fn):
        state = _build_state(entry)
        prompt = pb_fn(state)
        assert isinstance(prompt, str), f"{entry['id']}/{pb_name}: not a string"
        assert len(prompt) > 50, f"{entry['id']}/{pb_name}: too short ({len(prompt)})"


class TestGoldenSetBaseline:
    """Compare prompt lengths against persisted baseline (skipped if no baseline)."""

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=IDS)
    @pytest.mark.parametrize("pb_name,pb_fn", PROMPT_BUILDERS, ids=PROMPT_BUILDER_NAMES)
    def test_prompt_length_within_baseline(self, entry: dict, pb_name: str, pb_fn):
        check = os.environ.get("ARTICLE_CHECK_BASELINE", "").strip()
        if not check:
            pytest.skip("ARTICLE_CHECK_BASELINE not set")
        if not os.path.exists(BASELINE_PATH):
            pytest.skip("No baseline file found")

        import json
        with open(BASELINE_PATH, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        expected_len = baseline.get("entries", {}).get(entry["id"], {}).get("prompt_lengths", {}).get(pb_name, 0)
        if expected_len <= 0:
            pytest.skip(f"No baseline for {entry['id']}/{pb_name}")

        state = _build_state(entry)
        prompt = pb_fn(state)
        actual_len = len(prompt)
        ratio = actual_len / expected_len
        assert 0.8 <= ratio <= 1.2, (
            f"{entry['id']}/{pb_name}: {actual_len} vs baseline {expected_len} "
            f"(ratio={ratio:.2f}) — exceeds ±20% drift"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Invariant tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenSetInvariants:

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=IDS)
    def test_is_article_request_detected(self, entry: dict):
        assert is_article_request(entry["problem"]), f"{entry['id']}: should be detected as article request"

    @pytest.mark.parametrize("entry", [e for e in GOLDEN_SET if e.get("language")], ids=[e["id"] for e in GOLDEN_SET if e.get("language")])
    def test_language_detection(self, entry: dict):
        result = detect_language(entry["problem"])
        assert result == entry["language"], f"{entry['id']}: expected {entry['language']}, got {result}"

    @pytest.mark.parametrize("entry", [e for e in GOLDEN_SET if e.get("expect_deep")], ids=[e["id"] for e in GOLDEN_SET if e.get("expect_deep")])
    def test_deep_question_detected(self, entry: dict):
        from reasoner.application.flows.augmentation import is_deep_question
        assert is_deep_question(entry["problem"]), f"{entry['id']}: should be detected as deep question"

    def test_article_constants_sane(self):
        assert ARTICLE_MIN_SOURCE_COUNT >= 1
        assert ARTICLE_MAX_SOURCE_COUNT <= 50
        assert ARTICLE_SEARCH_RESULTS_PER_QUERY >= 3
        assert ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION >= 5
        assert 0.0 <= ARTICLE_MIN_CLAIM_SUPPORT_RATIO <= 1.0
        assert ARTICLE_CRITIC_MAX_WORDS >= 500

    def test_truncation_constants(self):
        assert hasattr(TRUNCATION, "PROMPT")
        assert hasattr(TRUNCATION, "SNIPPET")


class TestGoldenSetXssSafety:

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=IDS)
    def test_no_xss_in_prompts(self, entry: dict):
        state = _build_state(entry)
        xss = ["<script>", "javascript:", "onerror=", "onload="]
        for pb_name, pb_fn in PROMPT_BUILDERS:
            prompt = pb_fn(state)
            upper = prompt.upper()
            for pat in xss:
                assert pat.upper() not in upper, f"{entry['id']}/{pb_name}: XSS pattern '{pat}'"
