"""
Regression tests for pipeline bugs identified in real E2E runs.
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
import pytest
import asyncio
from dataclasses import asdict

from reasoner.pipeline import ReasonerPipeline
from reasoner.models import PipelineState, SolutionCandidate, PerspectiveType
from reasoner.llm import ProviderRouter


# ─────────────────────────────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────────────────────────────

class FakeProvider:
    """Minimal fake provider that returns canned strings."""
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    """Fake router that maps roles to JSON responses."""
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []
        self._primary = FakeProvider()
        self.primary = self._primary
        self.routing_table = {}

    def get(self, role: str):
        return self._primary

    async def call(self, role: str, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return self.responses.get(role, "{}"), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


# ─────────────────────────────────────────────────────────────────────
# Bug 1: Stress Test Hallucination
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stress_test_filters_language_hallucinations():
    """Stress tests mentioning Greek/parsing/encoding should be filtered out."""
    fake_response = json.dumps({
        "stress_tests": [
            {
                "scenario": "constraint_violation",
                "survival_rate": 0.5,
                "failure_mode": "missing or invalid Greek text causes parsing errors",
                "recovery_path": "ignore"
            }
        ]
    })
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "constructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "destructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "systemic": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "minimalist": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "scoring": json.dumps({"scores": []}),
        "stress_testing": fake_response,
        "synthesis": json.dumps({"core_solution": "done"}),
    })

    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = await pipeline.run("test problem")

    # The hallucinated stress test should be removed
    for st in state.stress_results:
        assert "greek" not in st.failure_mode.lower()
        assert "parsing" not in st.failure_mode.lower()


# ─────────────────────────────────────────────────────────────────────
# Bug 3: Recovery Path Leakage
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_path_does_not_pollute_errors():
    """Normal recovery path findings must not appear in state.errors."""
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "constructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "destructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "systemic": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "minimalist": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "scoring": json.dumps({
            "scores": [
                {
                    "perspective": "constructive",
                    "logical_consistency": 9,
                    "evidence_support": 9,
                    "failure_resilience": 9,
                    "feasibility": 9,
                    "total": 36,
                    "bias_flags": [],
                    "steel_man": "",
                    "confidence_vs_accuracy_penalty": 10.0,  # triggers recovery path
                }
            ]
        }),
        "recovery_path": json.dumps({"verification_findings": ["claim X is unsupported"]}),
        "stress_testing": json.dumps({"stress_tests": []}),
        "synthesis": json.dumps({"core_solution": "done"}),
    })

    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = await pipeline.run("test problem")

    # Errors should NOT contain recovery path diagnostics
    recovery_errors = [e for e in state.errors if "Recovery Path: Issues found" in e]
    assert not recovery_errors, f"Recovery path leaked into errors: {recovery_errors}"


# ─────────────────────────────────────────────────────────────────────
# Bug 4: Sources Format Coercion
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesis_coerces_string_sources():
    """String sources and markdown-link sources must become dicts."""
    router = FakeRouter({
        "classification": json.dumps({"task_type": "analytical"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": []}),
        "constructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "destructive": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "systemic": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "minimalist": json.dumps({"core_analysis": "ok", "key_insights": []}),
        "scoring": json.dumps({"scores": []}),
        "stress_testing": json.dumps({"stress_tests": []}),
        "synthesis": json.dumps({
            "core_solution": "done",
            "sources": [
                "Plain Title",
                "[Linked Title](https://example.com)",
                {"title": "Dict Title", "url": "https://dict.com"}
            ]
        }),
    })

    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = await pipeline.run("test problem")

    sources = state.final_solution.sources
    assert len(sources) == 3
    assert sources[0] == {"title": "Plain Title", "url": ""}
    assert sources[1] == {"title": "Linked Title", "url": "https://example.com"}
    assert sources[2] == {"title": "Dict Title", "url": "https://dict.com"}


# ─────────────────────────────────────────────────────────────────────
# Bug 6: Language Detection
# ─────────────────────────────────────────────────────────────────────

from reasoner.phases import detect_language
import reasoner.pipeline as _pipeline_module


@pytest.fixture(autouse=True)
def disable_token_cache():
    """Disable global token cache so fake-router tests don't cross-pollute."""
    original = _pipeline_module.TOKEN_OPTIMIZATION["caching"]
    old_cache = _pipeline_module.token_cache
    _pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
    _pipeline_module.token_cache = None
    yield
    _pipeline_module.TOKEN_OPTIMIZATION["caching"] = original
    _pipeline_module.token_cache = old_cache


def test_detect_language_greek():
    assert detect_language("Πρέπει να αναλύσεις αυτό το πρόβλημα.") == "Greek"


def test_detect_language_english_fallback():
    assert detect_language("This is clearly English.") == "English"


def test_detect_language_spanish():
    assert detect_language("¿Cómo deberíamos priorizar nuestra hoja de ruta?") == "Spanish"


def test_detect_language_german():
    assert detect_language("Wie sollen wir unsere Straße priorisieren?") == "German"


def test_detect_language_turkish():
    assert detect_language("Üçüncü çeyrekte yol haritamızı nasıl önceliklendirmeliyiz?") == "Turkish"


# ─────────────────────────────────────────────────────────────────────
# Prompt Enhancement
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prompt_enhancement_rewrites_problem():
    """The pipeline should rewrite the user prompt before classification."""
    responses = {
        "prompt_enhancement": json.dumps({"enhanced_problem": "A clearer, more specific version of the problem.", "improvements": ["added specificity"]}),
        "classification": json.dumps({"task_type": "analytical", "language": "English"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": [], "critical_sources": []}),
    }
    router = FakeRouter(responses)
    pipeline = ReasonerPipeline(router=router, top_k=2)
    state = PipelineState(problem="vague problem")
    await pipeline._phase_enhance_prompt(state)
    assert state.enhanced_problem == "A clearer, more specific version of the problem."
    assert "prompt_enhancement" in [c[0] for c in router.calls]


@pytest.mark.asyncio
async def test_prompt_enhancement_falls_back_to_original_on_failure():
    """If enhancement fails, the original prompt should be preserved."""
    responses = {
        "prompt_enhancement": "not valid json",
        "classification": json.dumps({"task_type": "analytical", "language": "English"}),
        "decomposition": json.dumps({"causal_chain": [], "assumptions": [], "failure_modes": [], "critical_sources": []}),
    }
    router = FakeRouter(responses)
    pipeline = ReasonerPipeline(router=router, top_k=2)
    state = PipelineState(problem="vague problem")
    await pipeline._phase_enhance_prompt(state)
    assert state.enhanced_problem == "vague problem"


# ─────────────────────────────────────────────────────────────────────
# Milestone 1 & 2: Predictive task type, decomposition hardening, search gating
# ─────────────────────────────────────────────────────────────────────

from reasoner.core.search import _should_include_result
from reasoner.models import TaskType


def test_should_include_result_rejects_raw_json_blobs():
    bad = {
        "url": "https://github.com/Wendy-Xiao/redundancy_reduction_longdoc/blob/master/vocabulary_pubmed.json",
        "content": " " * 50,
    }
    assert _should_include_result(bad) is False


def test_should_include_result_accepts_real_articles():
    good = {
        "url": "https://arstechnica.com/ai/2025/07/agi-may-be-impossible-to-define/",
        "content": "Artificial general intelligence remains a deeply contentious term among researchers, industry leaders, and philosophers debating its feasibility.",
    }
    assert _should_include_result(good) is True


def test_should_include_result_rejects_short_snippets():
    short = {
        "url": "https://example.com/article",
        "content": "Too short.",
    }
    assert _should_include_result(short) is False


def test_should_include_result_rejects_listicles():
    listicle = {
        "url": "https://example.com/startup-ideas",
        "title": "Top 10 Startup Ideas for Solopreneurs",
        "content": "This article lists ten great startup ideas that solopreneurs can use to build a profitable business in 2025.",
    }
    assert _should_include_result(listicle) is False


def test_task_type_has_predictive():
    assert TaskType.PREDICTIVE.value == "predictive"


@pytest.mark.asyncio
async def test_decomposition_prompt_demands_rationale_and_critical_sources():
    """The updated decomposition prompt must ask for rationale, source_hint, and critical_sources."""
    from reasoner.phases import decomposition_prompt
    state = PipelineState(problem="When will AGI arrive?")
    prompt = decomposition_prompt(state)
    assert "rationale" in prompt
    assert "source_hint" in prompt
    assert "critical_sources" in prompt
    assert "VERIFIED assumptions MUST cite a source_hint" in prompt


@pytest.mark.asyncio
async def test_fusion_parses_new_assumption_fields():
    """Fusion must preserve rationale, source_hint, and critical_sources in the decomposition dict."""
    # Classification and decomposition are one "fusion" call now.
    router = FakeRouter({
        "fusion": json.dumps({
            "task_type": "predictive",
            "causal_chain": [{"step": 1, "action": "Gather expert surveys", "produces": ["timeline estimates"]}],
            "assumptions": [
                {
                    "text": "Experts are willing to participate anonymously",
                    "label": "VERIFIED",
                    "rationale": "Bostrom 2014 survey had n=300",
                    "source_hint": "Bostrom survey"
                }
            ],
            "failure_modes": ["Definitional drift of 'AGI'"],
            "critical_sources": [{"url": "https://nickbostrom.com/papers/survey.pdf", "reason": "Primary expert survey"}]
        }),
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = await pipeline.run("When will AGI arrive?")

    dec = state.decomposition
    assert dec is not None
    assert dec.get("assumptions")[0].get("rationale") == "Bostrom 2014 survey had n=300"
    assert dec.get("assumptions")[0].get("source_hint") == "Bostrom survey"
    assert dec.get("critical_sources")[0]["url"] == "https://nickbostrom.com/papers/survey.pdf"


# ─────────────────────────────────────────────────────────────────────
# Milestone 4: Off-topic domain / acronym collision gating
# ─────────────────────────────────────────────────────────────────────

from reasoner.core.search import _should_include_result


def test_should_include_result_rejects_tax_agi_article():
    bad = {
        "url": "https://www.nerdwallet.com/taxes/learn/adjusted-gross-income-agi",
        "title": "Adjusted Gross Income (AGI): What It Is, How to Calculate",
        "content": "Artificial general intelligence is not discussed here. This is about taxes.",
    }
    assert _should_include_result(bad) is False


def test_should_include_result_rejects_political_bill_wikipedia():
    bad = {
        "url": "https://en.wikipedia.org/wiki/One_Big_Beautiful_Bill_Act",
        "title": "One Big Beautiful Bill Act",
        "content": "This article is about a U.S. federal statute passed by Congress.",
    }
    assert _should_include_result(bad) is False


def test_should_include_result_rejects_huggingface_vocab():
    bad = {
        "url": "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blame/refs%2Fpr%2F54/vocab.txt",
        "title": "vocab.txt",
        "content": "[PAD] [UNK] [CLS] [SEP] [MASK]",
    }
    assert _should_include_result(bad) is False


# ─────────────────────────────────────────────────────────────────────
# Milestone 4: Query enrichment
# ─────────────────────────────────────────────────────────────────────

from reasoner.pipeline import ReasonerPipeline


def test_enrich_query_adds_disambiguation_for_agi():
    enriched = ReasonerPipeline._enrich_query("AGI timeline", "When will AGI arrive? artificial general intelligence")
    assert "artificial general intelligence" in enriched


def test_enrich_query_leaves_unrelated_queries_unchanged():
    assert ReasonerPipeline._enrich_query("climate change", "What causes climate change?") == "climate change"
