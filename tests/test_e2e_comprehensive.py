"""
Comprehensive end-to-end tests for ARA Pipeline v2.1.

Covers:
- Prompt enhancement (opt-in)
- Language detection and synthesis language consistency
- Per-phase token tracking and model attribution
- Cross-lab fallback routing
- Cache behavior
- Multi-method execution

Fast fake-router tests run by default.
Slow real-API tests require --run-slow and OPENROUTER_API_KEY.
"""

import json
import os
import pytest
import pytest_asyncio
import asyncio
from dataclasses import asdict

import reasoner.api as api
from httpx import ASGITransport, AsyncClient
from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import get_preset, PRESETS
from reasoner.models import PipelineState


# ─────────────────────────────────────────────────────────────────────
# Fake Router Helpers
# ─────────────────────────────────────────────────────────────────────

class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "{}"


@pytest.fixture(autouse=True)
def disable_token_cache():
    """Disable global token cache so fake-router tests don't cross-pollute."""
    from reasoner.pipeline import TOKEN_OPTIMIZATION, token_cache as tc
    original = TOKEN_OPTIMIZATION["caching"]
    old_cache = tc
    TOKEN_OPTIMIZATION["caching"] = False
    import reasoner.pipeline as _pm
    _pm.token_cache = None
    yield
    TOKEN_OPTIMIZATION["caching"] = original
    _pm.token_cache = old_cache


class FakeRouter:
    """Configurable fake router for fast E2E testing."""
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
        resp = self.responses.get(role, "{}")
        return resp, {"model": "fake-model", "input_tokens": 10, "output_tokens": 15}

    def describe(self):
        return {"[primary]": "fake-model"}


def _make_classification_response(task_type="analytical", language="English"):
    return json.dumps({"task_type": task_type, "rationale": "test", "language": language})


def _make_decomposition_response():
    return json.dumps({
        "causal_chain": [{"step": 1, "action": "a", "produces": ["b"]}],
        "assumptions": [{"text": "x", "label": "HYPOTHESIS", "rationale": "y", "source_hint": ""}],
        "failure_modes": ["z"],
        "critical_sources": []
    })


def _make_fusion_response(task_type="analytical", language="English"):
    return json.dumps({
        "task_type": task_type,
        "task_rationale": "test",
        "language": language,
        "causal_chain": [{"step": 1, "action": "a", "produces": ["b"]}],
        "assumptions": [{"text": "x", "label": "HYPOTHESIS", "rationale": "y", "source_hint": ""}],
        "failure_modes": ["z"],
        "critical_sources": []
    })


def _make_perspective_response(perspective="constructive"):
    return json.dumps({
        "perspective": perspective,
        "core_analysis": f"analysis from {perspective}",
        "key_insights": ["insight 1"]
    })


def _make_critique_response():
    return json.dumps({
        "scores": [{
            "perspective": "constructive",
            "logical_consistency": 8,
            "evidence_support": 7,
            "practical_feasibility": 6,
            "novelty": 5,
            "confidence_vs_accuracy_penalty": 0.0,
            "steel_man": "good try"
        }]
    })


def _make_stress_test_response():
    return json.dumps({
        "stress_tests": [{
            "scenario": "optimal",
            "survival_rate": 0.8,
            "failure_mode": "none"
        }]
    })


def _make_synthesis_response(language="English"):
    return f"[SOLUTION]Test solution in {language}.[/SOLUTION] ```json\n{{\"critical_insights\": [\"ci\"], \"action_blueprint\": [{{\"step\": 1, \"action\": \"a\", \"time_horizon\": \"now\", \"go_criteria\": \"g\", \"fallback\": \"f\"}}], \"open_questions\": [\"oq\"], \"claim_labels\": [{{\"claim\": \"c\", \"label\": \"VERIFIED\"}}], \"meta_audit\": {{\"non_obvious_insight\": \"noi\", \"confidence_breakdown\": \"cb\", \"failure_mode_if_wrong\": \"fm\", \"uncertainty_quantification\": \"uq\"}}, \"sources\": []}}\n```"


def _build_fake_router(language="English", enhanced_problem: str | None = None):
    synth = _make_synthesis_response(language)
    base = {
        "prompt_enhancement": json.dumps({
            "enhanced_problem": enhanced_problem or "Enhanced version of the problem.",
            "improvements": ["added clarity"]
        }),
        "fusion": _make_fusion_response(task_type="analytical", language=language),
        "classification": _make_classification_response(language=language),
        "decomposition": _make_decomposition_response(),
        "primary": _make_perspective_response("constructive"),
        "constructive": _make_perspective_response("constructive"),
        "destructive": _make_perspective_response("destructive"),
        "systemic": _make_perspective_response("systemic"),
        "minimalist": _make_perspective_response("minimalist"),
        "scoring": _make_critique_response(),
        "stress_testing": _make_stress_test_response(),
        "synthesis": synth,
        "context_vetting": "{}",
        "generator_1": _make_perspective_response("constructive"),
        "critic_1": _make_critique_response(),
        "verifier": json.dumps({"verifications": []}),
        "meta_evaluator": json.dumps({"critic_reliability": {}, "meta_insight": ""}),
        "recovery_path": json.dumps({"recovery_plan": "", "root_causes": []}),
    }
    return FakeRouter(base)


# ─────────────────────────────────────────────────────────────────────
# Fast Fake-Router E2E Tests
# ─────────────────────────────────────────────────────────────────────

class TestPromptEnhancement:
    @pytest.mark.asyncio
    async def test_enhancement_opt_in_rewrites_problem(self):
        router = _build_fake_router()
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", enhance_prompt=True)
        state = await pipeline.run("vague problem")

        assert state.enhanced_problem != "vague problem"
        assert "prompt_enhancement" in [c[0] for c in router.calls]
        fusion_call = next(c for c in router.calls if c[0] == "fusion")
        assert "Enhanced version" in fusion_call[2]

    @pytest.mark.asyncio
    async def test_enhancement_opt_out_uses_original(self):
        router = _build_fake_router()
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget", enhance_prompt=False)
        state = await pipeline.run("vague problem")

        assert state.enhanced_problem == "vague problem"
        assert "prompt_enhancement" not in [c[0] for c in router.calls]


class TestLanguagePropagation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", ["Greek", "Spanish", "German", "Turkish"])
    async def test_synthesis_receives_language_instruction(self, lang):
        router = _build_fake_router(language=lang)
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget")
        state = await pipeline.run("test")

        assert state.language == lang
        synthesis_call = next(c for c in router.calls if c[0] == "synthesis")
        from reasoner.phases import get_language_instruction
        expected = get_language_instruction(PipelineState(problem="", language=lang))
        assert expected in synthesis_call[2]

    @pytest.mark.asyncio
    async def test_fusion_persists_language(self):
        router = _build_fake_router(language="Greek")
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget")
        state = await pipeline.run("test")
        assert state.language == "Greek"


class TestTokenAndModelTracking:
    @pytest.mark.asyncio
    async def test_phases_populate_token_usage(self):
        router = _build_fake_router()
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget")
        state = await pipeline.run("test")

        assert state.detailed_token_usage
        assert "fusion" in state.detailed_token_usage
        assert "synthesis" in state.detailed_token_usage
        for _role, tokens in state.detailed_token_usage.items():
            assert tokens.get("input", 0) >= 0
            assert tokens.get("output", 0) >= 0

    @pytest.mark.asyncio
    async def test_phases_populate_model_tracking(self):
        router = _build_fake_router()
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget")
        state = await pipeline.run("test")

        assert state.phase_models
        assert "fusion" in state.phase_models
        assert "synthesis" in state.phase_models


class TestPresetSpecificRouting:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("preset_id", [
        "multi-perspective-budget",
        "multi-perspective-premium",
        "iterative-budget",
        "debate-budget",
        "scientific-budget",
        "socratic-budget",
        "jury-budget",
        "pre-mortem-budget",
        "bayesian-budget",
        "dialectical-budget",
        "analogical-budget",
        "delphi-budget",
    ])
    async def test_preset_runs_to_completion_fake(self, preset_id):
        router = _build_fake_router()
        pipeline = ReasonerPipeline(router=router, preset_name=preset_id)
        state = await pipeline.run("What is 2+2?")

        assert state.task_type is not None
        assert state.final_solution is not None


class TestAPILLMErrorGracefulDegradation:
    @pytest.mark.asyncio
    async def test_pipeline_does_not_crash_on_empty_llm_response(self):
        # Provide minimal responses so pipeline doesn't hang, but empty for synthesis
        responses = {
            "fusion": _make_fusion_response(),
            "classification": _make_classification_response(),
            "decomposition": _make_decomposition_response(),
            "primary": "{}",
            "constructive": "{}",
            "destructive": "{}",
            "systemic": "{}",
            "minimalist": "{}",
            "scoring": _make_critique_response(),
            "stress_testing": _make_stress_test_response(),
            "synthesis": "",
            "context_vetting": "{}",
        }
        router = FakeRouter(responses)
        pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-budget")
        state = await pipeline.run("test")
        assert state.problem == "test"


# ─────────────────────────────────────────────────────────────────────
# API-Level Fast E2E Tests (Fake Router via monkeypatch)
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def api_client(monkeypatch):
    # Allow anonymous access for e2e tests that predate auth requirements
    monkeypatch.setenv("ENABLE_LEGACY_API_KEY", "true")
    async with AsyncClient(
        transport=ASGITransport(app=api.app), base_url="http://test"
    ) as c:
        yield c


class TestAPIPromptEnhancement:
    @pytest.mark.asyncio
    async def test_api_enhance_prompt_event(self, api_client, monkeypatch):
        captured = {}

        def _sse(data):
            return f"data: {json.dumps(data)}\n\n"

        async def fake_run_stream_cached(req, user_id=None):
            captured["enhance"] = req.enhance_prompt
            yield _sse({"type": "start", "routing": {"[primary]": "fake"}})
            if req.enhance_prompt:
                yield _sse({"type": "prompt_enhanced", "original": "vague", "enhanced": "Enhanced vague"})
            yield _sse({"type": "done", "solution": "ok", "errors": [], "tokens": {"total": 42}})

        monkeypatch.setattr(api, "run_stream_cached", fake_run_stream_cached)

        payload = {
            "problem": "vague",
            "preset": "multi-perspective-budget",
            "enhance_prompt": True,
            "no_cache": True,
        }
        async with api_client.stream("POST", "/api/run", json=payload, timeout=10) as response:
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        assert captured.get("enhance") is True
        enhanced = [e for e in events if e.get("type") == "prompt_enhanced"]
        assert enhanced
        assert enhanced[0]["enhanced"] == "Enhanced vague"


class TestAPITokenAndModelsInPhaseComplete:
    @pytest.mark.asyncio
    async def test_api_phase_complete_includes_tokens_and_models(self, api_client, monkeypatch):
        def _sse(data):
            return f"data: {json.dumps(data)}\n\n"

        async def fake_run_stream_cached(req, user_id=None):
            yield _sse({"type": "start", "routing": {"[primary]": "fake"}})
            yield _sse({
                "type": "phase_complete",
                "phase": 0,
                "name": "Classification",
                "data": {"task_type": "analytical", "tokens": {"input": 100, "output": 50}, "models": ["qwen3-turbo"]},
            })
            yield _sse({"type": "done", "solution": "ok", "errors": [], "tokens": {"total": 150}})

        monkeypatch.setattr(api, "run_stream_cached", fake_run_stream_cached)

        payload = {"problem": "test", "preset": "multi-perspective-budget", "no_cache": True}
        async with api_client.stream("POST", "/api/run", json=payload, timeout=10) as response:
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        complete = [e for e in events if e.get("type") == "phase_complete"][0]
        assert complete["data"]["tokens"]["input"] == 100
        assert complete["data"]["tokens"]["output"] == 50
        assert complete["data"]["models"] == ["qwen3-turbo"]


class TestAPISearch:
    @pytest.mark.asyncio
    async def test_api_search_returns_results(self, api_client, monkeypatch):
        import reasoner.core.search as _search_mod

        async def fake_search(*args, **kwargs):
            return [
                {"title": "Result 1", "url": "https://example.com/1", "snippet": "Snippet 1"},
                {"title": "Result 2", "url": "https://example.com/2", "snippet": "Snippet 2"},
            ]

        async def fake_get_discovery_client(**kwargs):
            return type("Client", (), {"search": fake_search})(), kwargs.get("source_type")

        async def fake_get_search_client(**kwargs):
            return type("Client", (), {"search": fake_search})(), kwargs.get("source_type")

        monkeypatch.setattr(_search_mod, "get_discovery_client", fake_get_discovery_client)
        monkeypatch.setattr(_search_mod, "get_search_client", fake_get_search_client)

        payload = {"query": "test query", "source_type": "general", "num_results": 5}
        response = await api_client.post("/api/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test query"
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_api_search_rejects_empty_query(self, api_client):
        payload = {"query": "   ", "source_type": "general"}
        response = await api_client.post("/api/search", json=payload)
        assert response.status_code == 422


class TestAPIDiscoverWidget:
    """BUG-001 E2E regression: /api/discover must work inside FastAPI's async loop."""

    @pytest.mark.asyncio
    async def test_api_discover_returns_results(self, api_client, monkeypatch):
        import reasoner.infrastructure.search.discovery as _discovery

        class FakeSearchClient:
            async def search(self, query, num_results=10, **kwargs):
                return [
                    {"title": f"{query} result", "url": "https://example.com", "content": "Content", "source": "test", "publishedDate": ""}
                ]

            async def close(self):
                return None

        async def fake_get_search_client(source_type=None):
            return FakeSearchClient(), source_type

        monkeypatch.setattr(_discovery, "get_search_client", fake_get_search_client)

        response = await api_client.get("/api/discover?topic=tech&mode=normal")
        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "tech"
        assert len(data["results"]) >= 1


class TestAPICriticalPhaseErrorHalt:
    """BUG-003 E2E regression: critical phase failure must halt pipeline before Synthesis."""

    @pytest.mark.asyncio
    async def test_api_run_halts_on_critical_phase_error(self, api_client, monkeypatch):
        fake_router = FakeRouter({
            "classification": _make_classification_response(),
        })
        monkeypatch.setattr(
            "reasoner.llm.ProviderRouter.from_model_ids",
            classmethod(lambda cls, **kwargs: fake_router),
        )

        async def fake_decompose(self, state):
            raise ValueError("simulated decomposition failure")

        monkeypatch.setattr("reasoner.pipeline.ReasonerPipeline._phase_1_decompose", fake_decompose)

        payload = {"problem": "test critical halt", "preset": "multi-perspective-budget", "no_cache": True}
        async with api_client.stream("POST", "/api/run", json=payload, timeout=10) as response:
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        phase_errors = [e for e in events if e.get("type") == "phase_error"]
        assert len(phase_errors) == 1
        assert "simulated decomposition failure" in phase_errors[0]["error"].lower()

        synthesis_completes = [
            e for e in events
            if e.get("type") == "phase_complete" and e.get("name") == "Synthesis"
        ]
        assert len(synthesis_completes) == 0

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1


# ─────────────────────────────────────────────────────────────────────
# Slow Real-API E2E Tests (require OPENROUTER_API_KEY + --run-slow)
# ─────────────────────────────────────────────────────────────────────

pytestmark_slow = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    ),
]


@pytest.mark.parametrize("preset_id", [
    "multi-perspective-budget",
    "multi-perspective-premium",
])
class TestRealLanguageConsistency:
    pytestmark = pytestmark_slow
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    @pytest.mark.parametrize("problem,expected_lang", [
        ("Πώς να προχωρήσω με το προϊόν μου;", "Greek"),
        ("¿Cómo debería priorizar mi roadmap?", "Spanish"),
        ("Wie soll ich meine Produkt-Roadmap priorisieren?", "German"),
        ("Üçüncü çeyrekte yol haritamızı nasıl önceliklendirmeliyiz?", "Turkish"),
    ])
    async def test_real_synthesis_responds_in_detected_language(self, preset_id, problem, expected_lang):
        preset = get_preset(preset_id)
        router = preset.build_router()
        pipeline = ReasonerPipeline(router=router, preset_name=preset_id, verbose=False)
        state = await pipeline.run(problem)

        assert state.language == expected_lang, f"Expected {expected_lang}, got {state.language}"
        assert state.final_solution is not None
        assert len(state.final_solution.core_solution) > 10


@pytest.mark.parametrize("preset_id", [
    "multi-perspective-budget",
    "multi-perspective-premium",
])
class TestRealPromptEnhancement:
    pytestmark = pytestmark_slow
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_real_enhancement_opt_in_produces_longer_prompt(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        problem = "product roadmap"

        pipeline_no_enhance = ReasonerPipeline(router=router, preset_name=preset_id, enhance_prompt=False, verbose=False)
        state_normal = await pipeline_no_enhance.run(problem)

        pipeline_enhance = ReasonerPipeline(router=router, preset_name=preset_id, enhance_prompt=True, verbose=False)
        state_enhanced = await pipeline_enhance.run(problem)

        assert state_enhanced.enhanced_problem != problem
        assert len(state_enhanced.enhanced_problem) >= len(problem)


@pytest.mark.parametrize("preset_id", [
    "multi-perspective-budget",
    "multi-perspective-premium",
    "debate-budget",
    "jury-premium",
])
class TestRealTokenAndModelTracking:
    pytestmark = pytestmark_slow
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_real_run_tracks_nonzero_tokens(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        pipeline = ReasonerPipeline(router=router, preset_name=preset_id, verbose=False)
        state = await pipeline.run("What is the capital of France?")

        total = sum(t.get("total", t.get("input", 0) + t.get("output", 0)) for t in state.detailed_token_usage.values())
        assert total > 0, f"Expected positive token usage for {preset_id}"

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_real_run_tracks_models_per_role(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        pipeline = ReasonerPipeline(router=router, preset_name=preset_id, verbose=False)
        state = await pipeline.run("What is the capital of France?")

        assert state.phase_models, f"Expected model tracking for {preset_id}"
        assert "classification" in state.phase_models or "synthesis" in state.phase_models


class TestRealAPICacheInvalidation:
    pytestmark = pytestmark_slow

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_api_cache_v2_invalidation(self, api_client):
        payload = {
            "problem": "What is 2+2?",
            "preset": "multi-perspective-budget",
            "top_k": 1,
            "sequential": True,
            "no_cache": False,
            "source_type": "general",
        }
        async with api_client.stream("POST", "/api/run", json=payload, timeout=120) as response:
            events_first = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events_first.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        done_first = [e for e in events_first if e.get("type") == "done"]
        assert done_first

        async with api_client.stream("POST", "/api/run", json=payload, timeout=120) as response:
            events_second = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events_second.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        start_events = [e for e in events_second if e.get("type") == "start"]
        if start_events and not done_first[0].get("errors"):
            completes = [e for e in events_second if e.get("type") == "phase_complete"]
            for c in completes:
                data = c.get("data", {})
                assert "tokens" in data, "Cached phase_complete missing tokens"

        clear_resp = await api_client.delete("/api/cache")
        assert clear_resp.status_code == 200
