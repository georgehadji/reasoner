"""
Unit tests for the Deep Read LLM extraction phase.
Uses mocks — no live scraping or LLM calls required.
"""

import json
import os
import pytest
from unittest.mock import patch, AsyncMock

from reasoner.pipeline import ReasonerPipeline
from reasoner.scraper import scrape_urls  # noqa: F401  — ensures module is loadable
from reasoner.models import PipelineState


class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []
        self._primary = FakeProvider()

    def get(self, role: str):
        return self._primary

    async def call(self, role: str, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return self.responses.get(role, "{}"), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


@pytest.fixture
def pipeline():
    router = FakeRouter({
        "classification": json.dumps({"task_type": "predictive"}),
        "decomposition": json.dumps({
            "causal_chain": [],
            "assumptions": [],
            "failure_modes": [],
            "critical_sources": [
                {"url": "https://example.com/article", "reason": "Key survey"}
            ],
        }),
    })
    return ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)


@pytest.mark.asyncio
async def test_deep_read_extracts_summary_on_scrape_success(pipeline):
    state = PipelineState(problem="When will AGI arrive?")
    state.vetted_context = [
        {"url": "https://example.com/article", "snippet": "Some snippet", "title": "Article"}
    ]

    scraped = [
        {
            "url": "https://example.com/article",
            "title": "Article Title",
            "content": "Full markdown content here.",
            "success": True,
        }
    ]

    extraction_response = json.dumps({
        "summary": "This article discusses expert predictions.",
        "key_facts": ["Median estimate 2040", "90th percentile 2075"],
        "relevant_quotes": ["'AGI remains undefined'"],
    })

    pipeline.router.responses["primary"] = extraction_response

    with patch("reasoner.scraper.scrape_urls", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = scraped
        await pipeline._phase_deep_read(state)

    assert len(state.vetted_context) == 1
    result = state.vetted_context[0]
    assert result["summary"] == "This article discusses expert predictions."
    assert result["key_facts"] == ["Median estimate 2040", "90th percentile 2075"]
    assert result["relevant_quotes"] == ["'AGI remains undefined'"]
    assert result["extraction_success"] is True
    assert result["deep_content"] == "Full markdown content here."

    # Ensure the prompt included the scraped content
    calls = pipeline.router.calls
    deep_read_calls = [c for c in calls if "Page Content" in c[2]]
    assert len(deep_read_calls) == 1


@pytest.mark.asyncio
async def test_deep_read_fallback_on_scrape_failure(pipeline):
    state = PipelineState(problem="When will AGI arrive?")
    state.vetted_context = [
        {"url": "https://example.com/article", "snippet": "Snippet from search", "title": "Article"}
    ]

    scraped = [
        {
            "url": "https://example.com/article",
            "title": "Article Title",
            "content": "",
            "success": False,
            "error": "HTTP 403",
        }
    ]

    fallback_response = json.dumps({
        "summary": "Likely contains expert survey data.",
        "key_facts": [],
        "relevant_quotes": [],
    })

    pipeline.router.responses["primary"] = fallback_response

    with patch("reasoner.scraper.scrape_urls", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = scraped
        await pipeline._phase_deep_read(state)

    result = state.vetted_context[0]
    assert result["summary"] == "Likely contains expert survey data."
    assert result["extraction_success"] is False

    # Ensure shallow-read prompt was used
    calls = pipeline.router.calls
    shallow_calls = [c for c in calls if "We could not fetch the full page" in c[2]]
    assert len(shallow_calls) == 1


@pytest.mark.asyncio
async def test_deep_read_legacy_mode_without_llm(pipeline):
    state = PipelineState(problem="When will AGI arrive?")
    state.vetted_context = [
        {"url": "https://example.com/article", "snippet": "Snippet", "title": "Article"}
    ]

    scraped = [
        {
            "url": "https://example.com/article",
            "title": "Article Title",
            "content": "Raw markdown content.",
            "success": True,
        }
    ]

    with patch("reasoner.scraper.scrape_urls", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = scraped
        # The flag is read from settings, which is built at import; patching the
        # environment alone has no effect.
        from reasoner.core.settings import settings

        with patch.object(settings, "REASONER_DEEP_READ_LLM", False):
            await pipeline._phase_deep_read(state)

    result = state.vetted_context[0]
    assert result["summary"] == "Raw markdown content."
    assert result["extraction_success"] is False

    # No LLM calls should have been made for deep/shallow reading
    llm_calls = [c for c in pipeline.router.calls if "Page Content" in c[2] or "We could not fetch" in c[2]]
    assert len(llm_calls) == 0


# ─────────────────────────────────────────────────────────────────────
# Milestone 5: Synthesis prompt includes structured deep-read data
# ─────────────────────────────────────────────────────────────────────

from reasoner.phases import synthesis_prompt


def test_synthesis_prompt_includes_deep_read_structures():
    state = PipelineState(problem="When will AGI arrive?")
    state.vetted_context = [
        {
            "url": "https://example.com/survey",
            "title": "Expert Survey",
            "summary": "Median estimate 2040.",
            "key_facts": ["2040 median", "2075 90th percentile"],
            "relevant_quotes": ["'Experts disagree'"],
            "vetting_flags": [],
        }
    ]
    prompt = synthesis_prompt(state)
    assert "with extracted summaries" in prompt
    assert "Median estimate 2040." in prompt
    assert "2040 median" in prompt
    assert "'Experts disagree'" in prompt


def test_synthesis_prompt_falls_back_to_discovery_results():
    state = PipelineState(problem="When will AGI arrive?")
    state.vetted_context = []
    state.web_discovery_results = [
        {"url": "https://fallback.com", "title": "Fallback Article"}
    ]
    prompt = synthesis_prompt(state)
    assert "Fallback Article" in prompt
    assert "with extracted summaries" not in prompt


# ─────────────────────────────────────────────────────────────────────
# Milestone 7: Cross-phase validation
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validation_warns_when_uncertain_assumptions_lack_evidence():
    router = FakeRouter({
        "classification": json.dumps({"task_type": "predictive"}),
        "decomposition": json.dumps({
            "causal_chain": [],
            "assumptions": [
                {"text": "AGI is measurable", "label": "HYPOTHESIS"}
            ],
            "failure_modes": [],
        }),
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="When will AGI arrive?")
    state.decomposition = {
        "causal_chain": [],
        "assumptions": [
            {"text": "AGI is measurable", "label": "HYPOTHESIS"}
        ],
        "failure_modes": [],
    }
    state.vetted_context = [
        {"url": "https://example.com", "summary": ""}  # empty summary
    ]

    # _validate_evidence_coverage is called inside run() after deep read;
    # we can exercise it directly here.
    pipeline._validate_evidence_coverage(state)

    # It should have logged a warning; we verify by checking state.phase_logs
    assert any("No extracted evidence" in entry for entry in state.phase_logs)


@pytest.mark.asyncio
async def test_validation_passes_when_evidence_exists():
    router = FakeRouter({
        "classification": json.dumps({"task_type": "predictive"}),
        "decomposition": json.dumps({
            "causal_chain": [],
            "assumptions": [
                {"text": "AGI is measurable", "label": "HYPOTHESIS"}
            ],
            "failure_modes": [],
        }),
    })
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", verbose=False)
    state = PipelineState(problem="When will AGI arrive?")
    state.decomposition = {
        "causal_chain": [],
        "assumptions": [
            {"text": "AGI is measurable", "label": "HYPOTHESIS"}
        ],
        "failure_modes": [],
    }
    state.vetted_context = [
        {"url": "https://example.com", "summary": "Experts define AGI as human-level performance."}
    ]

    pipeline._validate_evidence_coverage(state)

    assert not any("No extracted evidence" in entry for entry in state.phase_logs)
