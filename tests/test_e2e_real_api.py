"""
Real API end-to-end tests using actual OpenRouter API.

These tests hit the FastAPI /api/run endpoint with live LLM calls.
Run with: python -m pytest tests/test_e2e_real_api.py -v --run-slow
"""

import json
import os

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

import reasoner.api as api

pytestmark = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    ),
]

SIMPLE_PROBLEM = "What is the capital of France and why is it historically significant?"

METHOD_PRESETS = [
    ("multi_perspective", "multi-perspective-budget"),
    ("iterative", "iterative-budget"),
    ("debate", "debate-budget"),
    ("scientific", "scientific-budget"),
    ("socratic", "socratic-budget"),
    ("research", "research-budget"),
    ("jury", "jury-budget"),
    ("pre_mortem", "pre-mortem-budget"),
    ("bayesian", "bayesian-budget"),
    ("dialectical", "dialectical-budget"),
    ("analogical", "analogical-budget"),
    ("delphi", "delphi-budget"),
]


@pytest_asyncio.fixture(scope="module")
async def client():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=api.app), base_url="http://test"
    ) as c:
        yield c


class TestRealAPIRunStream:
    @pytest.mark.parametrize("method, preset_id", METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_api_run_stream_completes(self, client, method, preset_id):
        payload = {
            "problem": SIMPLE_PROBLEM,
            "preset": preset_id,
            "top_k": 2,
            "sequential": True,
            "no_cache": True,
            "source_type": "general",
        }

        async with client.stream("POST", "/api/run", json=payload, timeout=180) as response:
            assert response.status_code == 200
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        # Must have start event
        assert any(e.get("type") == "start" for e in events), f"Missing start event for {preset_id}"

        # Must have done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert done_events, f"Missing done event for {preset_id}"

        # No phase errors
        phase_errors = [e for e in events if e.get("type") == "phase_error"]
        assert not phase_errors, f"Phase errors for {preset_id}: {phase_errors}"

        # Done should not have critical pipeline errors
        done = done_events[-1]
        errors = done.get("errors", [])
        critical = [e for e in errors if "Pipeline processing error" in e]
        assert not critical, f"Critical API errors for {preset_id}: {critical}"

        # Should have phase_complete events
        completes = [e for e in events if e.get("type") == "phase_complete"]
        assert len(completes) >= 3, f"Expected at least 3 phase_complete events for {preset_id}, got {len(completes)}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_api_run_invalid_preset_returns_422(self, client):
        payload = {
            "problem": SIMPLE_PROBLEM,
            "preset": "nonexistent-preset-12345",
            "no_cache": True,
        }
        response = await client.post("/api/run", json=payload, timeout=30)
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_api_run_cache_roundtrip(self, client):
        payload = {
            "problem": "What is 2+2? Explain briefly.",
            "preset": "multi-perspective-budget",
            "top_k": 1,
            "sequential": True,
            "no_cache": False,
            "source_type": "general",
        }

        # First run - populate cache
        async with client.stream("POST", "/api/run", json=payload, timeout=120) as response:
            assert response.status_code == 200
            events_first = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events_first.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        done_first = [e for e in events_first if e.get("type") == "done"]
        assert done_first

        # Second run - should be cached
        async with client.stream("POST", "/api/run", json=payload, timeout=120) as response:
            assert response.status_code == 200
            events_second = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events_second.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        start_events = [e for e in events_second if e.get("type") == "start"]
        assert start_events
        # Cache is only used if the first run completed without errors
        if not done_first[0].get("errors"):
            assert start_events[0].get("cached") is True, "Expected cached flag on second run when first run had no errors"

        # Clean up cache for this test
        clear_resp = await client.delete("/api/cache")
        assert clear_resp.status_code == 200
