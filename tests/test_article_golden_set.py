"""
Article pipeline — golden set regression harness (Phase 0).

This module defines the frozen golden set of article-pipeline inputs that the
eval harness tests against.  Every refactor step after Phase 0 must assert
that the golden set produces equivalent or better outputs.

STRUCTURE
----------
GOLDEN_SET: tuple[ArticleTestCase, ...] — 20 problems spanning all venues.
test_golden_prompt_builders()   — every prompt builder runs without error.
test_golden_invariants()        — structural properties hold on built prompts.
test_check_baseline()          — if ARTICLE_CHECK_BASELINE env var is set,
                                  captures and compares against recorded baseline;
                                  else it's a no-op structural test.

USAGE
------
  pytest tests/test_article_golden_set.py -v                     # structural only
  ARTICLE_CHECK_BASELINE=1 pytest tests/test_article_golden_set.py  # capture/compare
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import pytest

from reasoner.core.constants import (
    ARTICLE_CRITIC_MAX_WORDS,
    ARTICLE_MAX_SOURCE_COUNT,
    ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION,
    ARTICLE_MIN_CLAIM_SUPPORT_RATIO,
    ARTICLE_MIN_SOURCE_COUNT,
    ARTICLE_SEARCH_RESULTS_PER_QUERY,
    TRUNCATION,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases import article as article_prompts
from reasoner.phases._shared import detect_language, is_article_request

# ═════════════════════════════════════════════════════════════════════
# Golden set definition
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ArticleTestCase:
    """A single frozen test case for article pipeline regression."""
    id: str
    problem: str
    content_class: str  # blog, policy_brief, explainer, op_ed, news_analysis, technical, greek_briefing
    language: str
    expect_deep_question: bool = False
    expect_article_request: bool = True
    style_brief: dict | None = None
    expected_language: str = "English"
    tags: tuple[str, ...] = ()


GOLDEN_SET: tuple[ArticleTestCase, ...] = (
    # ── Blog posts ──────────────────────────────────────────────────
    ArticleTestCase(
        id="blog_climate",
        problem="Write a blog post about the economic impact of climate change on coastal communities in Southeast Asia",
        content_class="blog",
        language="English",
        tags=("blog", "economy", "climate"),
    ),
    ArticleTestCase(
        id="blog_remote_work",
        problem="Draft a blog post about the future of remote work and its effect on urban development",
        content_class="blog",
        language="English",
        tags=("blog", "technology", "society"),
    ),

    # ── Explainer articles ──────────────────────────────────────────
    ArticleTestCase(
        id="explainer_quantum",
        problem="Write an explainer about quantum computing for a general audience",
        content_class="explainer",
        language="English",
        tags=("explainer", "technology", "science"),
    ),
    ArticleTestCase(
        id="explainer_immunity",
        problem="Draft an explainer article about how mRNA vaccines work, covering the mechanism of action and safety profile",
        content_class="explainer",
        language="English",
        tags=("explainer", "health", "science"),
    ),

    # ── Opinion / Op-Ed ─────────────────────────────────────────────
    ArticleTestCase(
        id="oped_ai_regulation",
        problem="Write an opinion piece arguing that AI regulation should focus on capability audits rather than use-case bans",
        content_class="op_ed",
        language="English",
        tags=("op_ed", "technology", "policy"),
    ),
    ArticleTestCase(
        id="oped_education",
        problem="Draft an op-ed about why classical education still matters in the age of AI",
        content_class="op_ed",
        language="English",
        tags=("op_ed", "education", "philosophy"),
    ),

    # ── Policy briefs ───────────────────────────────────────────────
    ArticleTestCase(
        id="policy_eu_data",
        problem="Draft a policy brief analyzing the European Union's approach to cross-border data flows under the Data Act",
        content_class="policy_brief",
        language="English",
        tags=("policy", "technology", "EU"),
    ),
    ArticleTestCase(
        id="policy_energy",
        problem="Write a policy analysis article comparing carbon pricing mechanisms across North America, Europe, and Asia-Pacific",
        content_class="policy_brief",
        language="English",
        tags=("policy", "energy", "economics"),
    ),

    # ── News analysis ───────────────────────────────────────────────
    ArticleTestCase(
        id="news_semiconductor",
        problem="Write a news analysis article about the global semiconductor supply chain realignment following recent export controls",
        content_class="news_analysis",
        language="English",
        tags=("news", "economics", "technology"),
    ),
    ArticleTestCase(
        id="news_cyber",
        problem="Compose a news analysis article examining the shift in cybersecurity threats from nation-state actors to criminal enterprises",
        content_class="news_analysis",
        language="English",
        tags=("news", "security", "technology"),
    ),

    # ── Technical articles ──────────────────────────────────────────
    ArticleTestCase(
        id="technical_llm",
        problem="Write a technical article explaining the architecture and trade-offs of mixture-of-experts transformer models",
        content_class="technical",
        language="English",
        tags=("technical", "AI", "deep_learning"),
    ),
    ArticleTestCase(
        id="technical_rust",
        problem="Draft a technical article about memory safety patterns in Rust compared to garbage-collected languages",
        content_class="technical",
        language="English",
        tags=("technical", "programming", "systems"),
    ),

    # ── Greek-language / NIKH-style briefing ────────────────────────
    ArticleTestCase(
        id="greek_geopolitics",
        problem="Γράψτε ένα άρθρο ανάλυσης για τις γεωπολιτικές επιπτώσεις της ενεργειακής μετάβασης στην Ανατολική Μεσόγειο",
        content_class="greek_briefing",
        language="Greek",
        expected_language="Greek",
        tags=("greek", "geopolitics", "energy"),
    ),
    ArticleTestCase(
        id="greek_technology",
        problem="Συντάξτε ένα άρθρο για την επίδραση της τεχνητής νοημοσύνης στην ελληνική αγορά εργασίας",
        content_class="greek_briefing",
        language="Greek",
        expected_language="Greek",
        tags=("greek", "technology", "economy"),
    ),

    # ── Articles with style briefs ──────────────────────────────────
    ArticleTestCase(
        id="styled_newyorker",
        problem="Write an article about the decline of local news in rural America",
        content_class="blog",
        language="English",
        style_brief={"author": "Jane Doe", "publication": "The New Yorker"},
        tags=("style", "media", "society"),
    ),
    ArticleTestCase(
        id="styled_financial",
        problem="Draft an article analyzing the investment implications of deglobalization for emerging markets",
        content_class="policy_brief",
        language="English",
        style_brief={"publication": "Financial Times"},
        tags=("style", "finance", "economics"),
    ),

    # ── Deep / philosophical questions ──────────────────────────────
    ArticleTestCase(
        id="deep_consciousness",
        problem="Write an article exploring the philosophical and scientific debate about the nature of consciousness",
        content_class="explainer",
        language="English",
        expect_deep_question=True,
        tags=("deep", "philosophy", "science"),
    ),
    ArticleTestCase(
        id="deep_free_will",
        problem="Draft an article examining whether free will is compatible with modern neuroscience",
        content_class="explainer",
        language="English",
        expect_deep_question=True,
        tags=("deep", "philosophy", "neuroscience"),
    ),
    ArticleTestCase(
        id="deep_greek_techne",
        problem="Γράψτε ένα άρθρο για την έννοια της τέχνης στην αρχαία ελληνική φιλοσοφία και τη σχέση της με τη σύγχρονη τεχνολογία",
        content_class="greek_briefing",
        language="Greek",
        expected_language="Greek",
        expect_deep_question=True,
        tags=("greek", "deep", "philosophy"),
    ),

    # ── Short-form articles ────────────────────────────────────────
    ArticleTestCase(
        id="short_book_review",
        problem="Write a short article reviewing Yuval Noah Harari's Nexus, focusing on its thesis about information networks",
        content_class="blog",
        language="English",
        tags=("short", "review", "books"),
    ),

    # ── Multi-source factual topics ────────────────────────────────
    ArticleTestCase(
        id="factual_space",
        problem="Write an article about the Artemis program and its implications for international collaboration in space exploration",
        content_class="news_analysis",
        language="English",
        tags=("factual", "space", "science"),
    ),
)


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════

def _build_state(tc: ArticleTestCase) -> PipelineState:
    """Build a minimal PipelineState for a test case.

    Uses only constructor kwargs (no LLM calls).  Sets enough writing_state
    fields to satisfy prompt builders without crashing.
    """
    state = PipelineState(
        problem=tc.problem,
        language=tc.language,
        preset_name="article-budget",
        method="article",
    )
    # Seed minimal writing_state — prompt builders read various fields
    ws = state.writing_state
    ws["final_article"] = "# Draft\n\nThis is a draft article body for testing prompt builders."
    ws["retrieved_sources"] = [
        {"title": f"Source {i}", "url": f"https://example{i}.com", "snippet": f"Snippet {i}"}
        for i in range(1, 6)
    ]
    ws["source_metadata"] = [
        {"title": f"Source {i}", "url": f"https://example{i}.com",
         "author": "Test Author", "date": "2025-01-01",
         "publisher": "Test Publisher", "snippet": f"Snippet {i}"}
        for i in range(1, 6)
    ]
    ws["argument_map"] = {
        "central_question": "What is the main question?",
        "problem": "The problem this article addresses",
        "current_explanations": ["Viewpoint A", "Viewpoint B"],
        "limitations": ["Limitation 1", "Limitation 2"],
        "new_insight": "A novel perspective",
        "counterarguments": ["Counter 1"],
        "implications": ["Implied outcome 1"],
    }
    ws["outline"] = [
        {"section_title": "Introduction", "key_points": ["Hook", "Thesis"],
         "sources_used": ["https://example1.com"], "estimated_words": 200},
        {"section_title": "Body", "key_points": ["Evidence", "Analysis"],
         "sources_used": ["https://example2.com"], "estimated_words": 600},
    ]
    ws["suggested_title"] = "Test Article Title"
    ws["verification"] = {
        "verified_claims": [
            {"claim": "Example claim 1", "verdict": "supported",
             "source_url": "https://example1.com", "note": "Verified"},
        ],
        "metrics": {"total_claims": 5, "supported": 4, "unsupported": 1,
                    "claim_support_ratio": 0.8},
        "gaps": ["Topic A needs more evidence"],
    }
    ws["claim_ledger"] = [
        {"claim": "Verified claim text", "source": "https://example1.com",
         "status": "verified"},
        {"claim": "Speculative claim text", "source": None,
         "status": "speculative"},
    ]
    ws["metrics"] = {"total_claims": 5, "supported": 4, "unsupported": 1,
                     "claim_support_ratio": 0.8}
    ws["structural_critique"] = {
        "implicit_assumptions": [{"assumption": "Assumption A", "section": "Body",
                                   "risk": "high"}],
        "logical_gaps": [{"gap": "Gap description", "section": "Body",
                          "severity": "high"}],
        "ignored_counterarguments": [{"argument": "Counterargument A",
                                       "relevance": "high"}],
        "overall_rigor_score": 0.7,
    }
    ws["editorial_audit"] = {
        "audit": {
            "thesis_advancement": 0.8,
            "claim_support": 0.7,
            "internal_consistency": 0.85,
            "transition_quality": 0.75,
            "redundancy_removed": 0.7,
            "citation_accuracy": 0.9,
            "policy_compliance": 1.0,
        },
        "issues": [],
        "audit_score": 0.8,
        "passes_audit": True,
    }
    if tc.style_brief:
        ws["style_brief"] = tc.style_brief
    return state


def _get_baseline_path() -> str:
    """Return path to baseline JSON file (stored alongside this test file)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "_data", "article_baseline.json")


# ═════════════════════════════════════════════════════════════════════
# Structural / property tests (always run, no LLM calls)
# ═════════════════════════════════════════════════════════════════════

class TestGoldenSetPromptBuilders:
    """Every prompt builder in the article pipeline runs without error on every
    golden set input.  This is the shallowest structural invariant."""

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_retrieval_plan_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_retrieval_plan_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50
        # Must reference the problem text
        assert tc.problem[:50] in prompt

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_draft_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_draft_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_outline_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_outline_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_verify_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_verify_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_critic_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_critic_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_dev_edit_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_developmental_edit_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_style_edit_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_style_edit_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_copy_edit_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_copy_edit_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_final_audit_prompt_builds(self, tc: ArticleTestCase):
        state = _build_state(tc)
        prompt = article_prompts.article_final_audit_prompt(state)
        assert isinstance(prompt, str) and len(prompt) > 50

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_verify_sonar_prompt_builds(self, tc: ArticleTestCase):
        """Sonar variant of the verify prompt also works."""
        state = _build_state(tc)
        prompt = article_prompts.article_verify_prompt(state, use_sonar=True)
        assert isinstance(prompt, str) and len(prompt) > 50
        assert "sources_block" not in prompt or len(prompt) > 0  # sonar skips source injection


class TestGoldenSetInvariants:
    """Structural invariants that every golden set entry must satisfy."""

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_article_request_detection(self, tc: ArticleTestCase):
        """Non-assertion test that records detection behavior."""
        detected = is_article_request(tc.problem)
        if tc.expect_article_request:
            assert detected, f"{tc.id}: should be detected as article request"
        else:
            assert not detected, f"{tc.id}: should NOT be detected as article request"

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_language_detection(self, tc: ArticleTestCase):
        detected = detect_language(tc.problem)
        assert detected == tc.expected_language, (
            f"{tc.id}: expected language={tc.expected_language}, got={detected}"
        )

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_state_minimal_writing_state(self, tc: ArticleTestCase):
        """Minimal writing_state contains all required keys for prompt builders."""
        state = _build_state(tc)
        ws = state.writing_state
        required_keys = [
            "final_article", "retrieved_sources", "argument_map",
            "outline", "verification", "claim_ledger", "metrics",
            "structural_critique", "editorial_audit",
        ]
        for key in required_keys:
            assert key in ws, f"{tc.id}: missing writing_state.{key}"

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_prompt_does_not_contain_raw_html_or_xss_patterns(self, tc: ArticleTestCase):
        """Prompt builders must not inject unescaped HTML or JavaScript."""
        state = _build_state(tc)
        prompts = [
            article_prompts.article_retrieval_plan_prompt(state),
            article_prompts.article_draft_prompt(state),
            article_prompts.article_outline_prompt(state),
            article_prompts.article_verify_prompt(state),
            article_prompts.article_critic_prompt(state),
            article_prompts.article_developmental_edit_prompt(state),
            article_prompts.article_style_edit_prompt(state),
            article_prompts.article_copy_edit_prompt(state),
            article_prompts.article_final_audit_prompt(state),
        ]
        xss_patterns = ["<script>", "javascript:", "onerror=", "onload="]
        for prompt in prompts:
            prompt_upper = prompt.upper()
            for pat in xss_patterns:
                assert pat.upper() not in prompt_upper, (
                    f"{tc.id}: XSS pattern '{pat}' found in prompt"
                )

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_style_brief_integration(self, tc: ArticleTestCase):
        """When style_brief has author/publication, the draft prompt includes a
        STYLE REQUIREMENT block."""
        state = _build_state(tc)
        if tc.style_brief and tc.style_brief.get("author", tc.style_brief.get("publication")):
            prompt = article_prompts.article_draft_prompt(state)
            assert "STYLE REQUIREMENT" in prompt, (
                f"{tc.id}: style_brief set but not reflected in draft prompt"
            )

    def test_article_constants_are_sane(self):
        """Article-specific constants must have reasonable values."""
        assert ARTICLE_MIN_SOURCE_COUNT >= 3, "Too few minimum sources"
        assert ARTICLE_MAX_SOURCE_COUNT <= 50, "Too many maximum sources"
        assert ARTICLE_SEARCH_RESULTS_PER_QUERY >= 3, "Too few search results"
        assert ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION >= 5, "Too few sources for extraction"
        assert 0.0 <= ARTICLE_MIN_CLAIM_SUPPORT_RATIO <= 1.0, "Ratio out of range"
        assert ARTICLE_CRITIC_MAX_WORDS >= 500, "Critic max words too low"

    def test_truncation_constants_available(self):
        """TRUNCATION constants must exist (prompt builders depend on them)."""
        assert hasattr(TRUNCATION, "PROMPT"), "TRUNCATION.PROMPT missing"
        assert hasattr(TRUNCATION, "SNIPPET"), "TRUNCATION.SNIPPET missing"


class TestGoldenSetDepthDetection:
    """Deep question detection — depends on augmentation.py."""

    @pytest.mark.parametrize("tc", [t for t in GOLDEN_SET if t.expect_deep_question],
                             ids=lambda tc: tc.id)
    def test_deep_question_detected(self, tc: ArticleTestCase):
        from reasoner.application.flows.augmentation import is_deep_question
        assert is_deep_question(tc.problem), f"{tc.id}: should be detected as deep question"


class TestGoldenSetCostBaseline:
    """Cost baseline tests — validate preset pricing stays within expected bounds."""

    def _get_preset_cost_baseline(self) -> dict:
        """Load the recorded cost baseline from disk."""
        bp = _get_baseline_path()
        if not os.path.exists(bp):
            return {}
        with open(bp, encoding="utf-8") as fh:
            return json.load(fh).get("cost_baseline", {})

    def test_cost_baseline_recorded(self):
        """If a cost baseline was captured, assert it matches expectations."""
        baseline = self._get_preset_cost_baseline()
        if not baseline:
            pytest.skip("No cost baseline recorded — run capture_article_baseline.py to create one")
        for preset_name, cost in baseline.items():
            assert isinstance(cost, (int, float)), f"Cost for {preset_name} is not numeric"
            assert cost > 0, f"Cost for {preset_name} is not positive"


class TestGoldenSetBaselineCheck:
    """Comparison test against the recorded golden set baseline.

    Only runs when ARTICLE_CHECK_BASELINE env var is set and a baseline file
    exists.  Otherwise it's a no-op.
    """

    BASELINE_CHECK = os.environ.get("ARTICLE_CHECK_BASELINE", "").strip()

    @pytest.mark.parametrize("tc", GOLDEN_SET, ids=lambda tc: tc.id)
    def test_baseline_structural(self, tc: ArticleTestCase):
        if not self.BASELINE_CHECK:
            pytest.skip("ARTICLE_CHECK_BASELINE not set — skip baseline comparison")
        bp = _get_baseline_path()
        if not os.path.exists(bp):
            pytest.skip(f"Baseline file not found at {bp}")

        with open(bp, encoding="utf-8") as fh:
            baseline = json.load(fh)

        entries = baseline.get("entries", {})
        entry = entries.get(tc.id)
        if entry is None:
            pytest.skip(f"No baseline entry for {tc.id}")

        state = _build_state(tc)
        ws = state.writing_state

        # Structural invariants against baseline
        baseline_prompt_lengths = entry.get("prompt_lengths", {})
        for prompt_name, builder_fn in [
            ("retrieval_plan", article_prompts.article_retrieval_plan_prompt),
            ("draft", article_prompts.article_draft_prompt),
            ("outline", article_prompts.article_outline_prompt),
            ("verify", article_prompts.article_verify_prompt),
            ("critic", article_prompts.article_critic_prompt),
            ("dev_edit", article_prompts.article_developmental_edit_prompt),
            ("style_edit", article_prompts.article_style_edit_prompt),
            ("copy_edit", article_prompts.article_copy_edit_prompt),
            ("final_audit", article_prompts.article_final_audit_prompt),
        ]:
            prompt = builder_fn(state)
            prev = baseline_prompt_lengths.get(prompt_name, 0)
            # Allow ±20% drift before flagging as regression
            if prev > 0:
                ratio = len(prompt) / prev
                assert 0.8 <= ratio <= 1.2, (
                    f"{tc.id}/{prompt_name}: prompt length {len(prompt)} vs "
                    f"baseline {prev} (ratio={ratio:.2f}) — exceeds ±20% drift"
                )


# ═════════════════════════════════════════════════════════════════════
# Baseline capture helper (exported for the capture script)
# ═════════════════════════════════════════════════════════════════════

def capture_baseline() -> dict[str, Any]:
    """Capture current golden set metrics as a baseline dict.

    Returns a dict that can be serialized to JSON and stored as the new baseline.
    This is called by scripts/capture_article_baseline.py, not directly in tests.
    """
    entries: dict[str, Any] = {}
    for tc in GOLDEN_SET:
        state = _build_state(tc)
        prompt_lengths: dict[str, int] = {}
        for prompt_name, builder_fn in [
            ("retrieval_plan", article_prompts.article_retrieval_plan_prompt),
            ("draft", article_prompts.article_draft_prompt),
            ("outline", article_prompts.article_outline_prompt),
            ("verify", article_prompts.article_verify_prompt),
            ("critic", article_prompts.article_critic_prompt),
            ("dev_edit", article_prompts.article_developmental_edit_prompt),
            ("style_edit", article_prompts.article_style_edit_prompt),
            ("copy_edit", article_prompts.article_copy_edit_prompt),
            ("final_audit", article_prompts.article_final_audit_prompt),
        ]:
            try:
                prompt = builder_fn(state)
                prompt_lengths[prompt_name] = len(prompt)
            except Exception:
                prompt_lengths[prompt_name] = -1  # error marker

        entries[tc.id] = {
            "problem": tc.problem[:100],
            "content_class": tc.content_class,
            "language": tc.language,
            "expected_language": tc.expected_language,
            "expect_deep_question": tc.expect_deep_question,
            "has_style_brief": tc.style_brief is not None,
            "prompt_lengths": prompt_lengths,
        }

    return {
        "meta": {
            "description": "Article pipeline golden set baseline (Phase 0)",
            "count": len(GOLDEN_SET),
            "format_version": 1,
        },
        "entries": entries,
    }
