"""
Unit tests for the HyperGate sub-agent system.

Uses a FakeRouter that returns configurable JSON per router.call() invocation so
every test is deterministic and offline.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.hypergate import HyperGateAgent
from reasoner.hypergate.models import HyperContext, SubAgentInput, SubAgentOutput
from reasoner.hypergate.sub_agents import (
    ComplexityEstimatorSubAgent,
    DirectDetectorSubAgent,
    LanguageDetectorSubAgent,
    MethodClassifierSubAgent,
    TieBreakerSubAgent,
    WebSearchDetectorSubAgent,
)

# ── Helpers ───────────────────────────────────────────────────────────


class FakeProvider:
    def __init__(self, model: str = "fake-model"):
        self.model = model
        self.last_input_tokens = 10
        self.last_output_tokens = 5
        self.last_cost_usd = 0.0


def make_router(*responses: str) -> Any:
    """
    Build a fake ProviderRouter whose call() returns each response in sequence.
    After exhausting the list, repeats the last response.
    """
    provider = FakeProvider()
    router = MagicMock()
    router.get.return_value = provider

    call_results = list(responses)
    call_count = {"n": 0}

    async def fake_call(role, system_prompt, user_prompt, **kwargs):
        idx = min(call_count["n"], len(call_results) - 1)
        call_count["n"] += 1
        return call_results[idx], {"input_tokens": 10, "output_tokens": 5, "model": "fake-model"}

    router.call = fake_call
    return router


def _j(**kwargs) -> str:
    return json.dumps(kwargs)


# ── BaseSubAgent cache ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_base_sub_agent_cache():
    """Second call with same problem returns cached result without LLM."""
    agent = LanguageDetectorSubAgent()
    agent._cache.clear()

    router = make_router(_j(language="Greek", confidence=0.95))
    inp = SubAgentInput(problem="Ποιο είναι το νόημα της ζωής;", agent_name="test")

    out1 = await agent.execute(inp, router)
    out2 = await agent.execute(inp, router)

    assert out1 is out2  # same object from cache
    assert out1.result["language"] == "Greek"


@pytest.mark.asyncio
async def test_base_sub_agent_graceful_failure():
    """Exception in LLM call → SubAgentOutput with error set, confidence=0."""
    agent = DirectDetectorSubAgent()
    agent._cache.clear()

    broken_router = MagicMock()
    broken_router.get.return_value = FakeProvider()
    broken_router.call = AsyncMock(side_effect=RuntimeError("LLM down"))

    inp = SubAgentInput(problem="Does this work?", agent_name="test")
    out = await agent.execute(inp, broken_router)

    assert out.error is not None
    assert out.confidence == 0.0


# ── Individual sub-agent parsing ─────────────────────────────────────


@pytest.mark.asyncio
async def test_language_detector():
    agent = LanguageDetectorSubAgent()
    agent._cache.clear()
    router = make_router(_j(language="Spanish", confidence=0.92))
    inp = SubAgentInput(problem="¿Cómo estás?", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["language"] == "Spanish"
    assert out.confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_complexity_estimator_complex():
    agent = ComplexityEstimatorSubAgent()
    agent._cache.clear()
    router = make_router(_j(complexity="complex", confidence=0.88))
    inp = SubAgentInput(problem="Design a distributed caching strategy.", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["complexity"] == "complex"


@pytest.mark.asyncio
async def test_complexity_estimator_invalid_defaults_to_medium():
    agent = ComplexityEstimatorSubAgent()
    agent._cache.clear()
    router = make_router(_j(complexity="extreme", confidence=0.7))
    inp = SubAgentInput(problem="Something", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["complexity"] == "medium"


@pytest.mark.asyncio
async def test_direct_detector_true():
    agent = DirectDetectorSubAgent()
    agent._cache.clear()
    router = make_router(_j(is_direct=True, confidence=0.95, rationale="Simple greeting"))
    inp = SubAgentInput(problem="Hi!", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["is_direct"] is True
    assert out.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_web_detector_needs_search():
    agent = WebSearchDetectorSubAgent()
    agent._cache.clear()
    router = make_router(_j(needs_search=True, confidence=0.9, rationale="Current event"))
    inp = SubAgentInput(problem="What's the weather in Athens today?", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["needs_search"] is True


@pytest.mark.asyncio
async def test_method_classifier_category_b():
    agent = MethodClassifierSubAgent()
    agent._cache.clear()
    router = make_router(_j(category="B", confidence=0.85, rationale="adversarial viewpoints"))
    inp = SubAgentInput(problem="Nuclear vs solar energy debate.", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["category"] == "B"
    assert out.result["method"] == "debate"
    assert out.result["action"] == "pipeline"


@pytest.mark.asyncio
async def test_method_classifier_unknown_category_defaults_e():
    agent = MethodClassifierSubAgent()
    agent._cache.clear()
    router = make_router(_j(category="Z", confidence=0.9, rationale="unknown"))
    inp = SubAgentInput(problem="Anything.", agent_name="test")
    out = await agent.execute(inp, router)
    assert out.result["category"] == "E"
    assert out.result["method"] == "multi_perspective"


# ── TieBreakerSubAgent ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tie_breaker_returns_pipeline():
    agent = TieBreakerSubAgent()
    agent._cache.clear()
    router = make_router(_j(action="pipeline", method="debate", confidence=0.78, rationale="TB resolved"))
    inp = SubAgentInput(problem="Complex strategy.", agent_name="test", context={"dummy": True})
    out = await agent.execute(inp, router)
    assert out.result["action"] == "pipeline"
    assert out.result["method"] == "debate"


@pytest.mark.asyncio
async def test_tie_breaker_invalid_method_defaults():
    agent = TieBreakerSubAgent()
    agent._cache.clear()
    router = make_router(_j(action="pipeline", method="nonexistent_method", confidence=0.6, rationale="x"))
    inp = SubAgentInput(problem="X", agent_name="test", context={})
    out = await agent.execute(inp, router)
    assert out.result["method"] == "multi_perspective"


# ── HyperGateAgent integration ────────────────────────────────────────


def _make_phase1_router(
    lang="English", lang_conf=0.99,
    cpx="simple", cpx_conf=0.95,
    is_direct=True, dir_conf=0.90, dir_rationale="simple greeting",
    needs_search=False, web_conf=0.1, web_rationale="no real-time data",
    category="E", method_conf=0.5, method_rationale="general",
):
    """Build a router that returns the 5 Phase-1 responses in order."""
    responses = [
        _j(language=lang, confidence=lang_conf),
        _j(complexity=cpx, confidence=cpx_conf),
        _j(is_direct=is_direct, confidence=dir_conf, rationale=dir_rationale),
        _j(needs_search=needs_search, confidence=web_conf, rationale=web_rationale),
        _j(category=category, confidence=method_conf, rationale=method_rationale),
    ]
    return make_router(*responses)


@pytest.mark.asyncio
async def test_hypergate_short_prompt_direct():
    """Problems < 10 chars bypass sub-agents entirely."""
    router = make_router()  # will not be called
    agent = HyperGateAgent(router)
    decision = await agent.decide("hi")
    assert decision.action == "direct"
    assert decision.confidence == 1.0


@pytest.mark.asyncio
async def test_hypergate_routes_to_direct():
    """Simple greeting → DirectDetector wins → action=direct."""
    router = _make_phase1_router(
        is_direct=True, dir_conf=0.92,
        cpx="simple", cpx_conf=0.95,
        method_conf=0.3,  # low method confidence — no conflict
    )
    agent = HyperGateAgent(router)
    decision = await agent.decide("Hello, how are you today?")
    assert decision.action == "direct"
    assert decision.confidence >= 0.80


@pytest.mark.asyncio
async def test_hypergate_routes_to_web_search():
    """Real-time query → WebDetector wins → action=web_search."""
    router = _make_phase1_router(
        is_direct=False, dir_conf=0.05,
        needs_search=True, web_conf=0.91,
        cpx="simple", cpx_conf=0.8,
        method_conf=0.3,
    )
    agent = HyperGateAgent(router)
    decision = await agent.decide("What's the score of tonight's game?")
    assert decision.action == "web_search"
    assert decision.confidence >= 0.75


@pytest.mark.asyncio
async def test_hypergate_routes_to_pipeline():
    """Complex problem → MethodClassifier wins → action=pipeline."""
    router = _make_phase1_router(
        is_direct=False, dir_conf=0.05,
        needs_search=False, web_conf=0.05,
        cpx="complex", cpx_conf=0.9,
        category="I", method_conf=0.82, method_rationale="bayesian reasoning",
    )
    agent = HyperGateAgent(router)
    decision = await agent.decide("Estimate the probability of this startup succeeding given these factors.")
    assert decision.action == "pipeline"
    assert decision.method == "bayesian"
    assert decision.confidence >= 0.70


@pytest.mark.asyncio
async def test_hypergate_tiebreaker_called_on_ambiguous():
    """All Phase-1 signals between 0.45–0.70 → TieBreaker runs."""
    # Phase-1 responses (all low confidence)
    phase1_responses = [
        _j(language="English", confidence=0.99),
        _j(complexity="medium", confidence=0.8),
        _j(is_direct=False, confidence=0.50, rationale="borderline"),
        _j(needs_search=False, confidence=0.48, rationale="borderline"),
        _j(category="E", confidence=0.55, rationale="borderline"),
    ]
    # TieBreaker response (6th call)
    tb_response = _j(action="pipeline", method="scientific", confidence=0.75, rationale="TB resolved")
    router = make_router(*phase1_responses, tb_response)

    agent = HyperGateAgent(router)
    decision = await agent.decide("An ambiguous borderline problem that is hard to classify.")
    assert decision.action == "pipeline"
    assert decision.method == "scientific"


@pytest.mark.asyncio
async def test_hypergate_all_fail_fallback():
    """All sub-agents raise → hard fallback to pipeline+multi_perspective."""
    broken_router = MagicMock()
    broken_router.get.return_value = FakeProvider()
    broken_router.call = AsyncMock(side_effect=RuntimeError("all broken"))

    agent = HyperGateAgent(broken_router)
    decision = await agent.decide("Some complex problem that needs reasoning.")
    assert decision.action == "pipeline"
    assert decision.method == "multi_perspective"
    assert decision.confidence == 0.0


@pytest.mark.asyncio
async def test_hypergate_top_level_cache():
    """Identical problem on second call returns cached GateDecision."""
    router = _make_phase1_router(
        is_direct=True, dir_conf=0.92,
        cpx="simple", cpx_conf=0.95,
        method_conf=0.3,
    )
    call_count = {"n": 0}
    original_call = router.call

    async def counting_call(*args, **kwargs):
        call_count["n"] += 1
        return await original_call(*args, **kwargs)

    router.call = counting_call

    agent = HyperGateAgent(router)
    problem = "Hello, how are you today? (cache test)"
    d1 = await agent.decide(problem)
    calls_after_first = call_count["n"]

    d2 = await agent.decide(problem)
    assert call_count["n"] == calls_after_first  # no new LLM calls
    assert d1.action == d2.action
    assert d1.confidence == d2.confidence


# ── HyperContext ──────────────────────────────────────────────────────


def _dummy_output(agent_name: str, result: dict) -> SubAgentOutput:
    return SubAgentOutput(
        agent_name=agent_name, result=result, confidence=0.9,
        reasoning="ok", tokens_in=5, tokens_out=5, model="fake", duration_ms=10.0,
    )


def test_hyper_context_language_property():
    ctx = HyperContext(
        problem="test",
        lang_output=_dummy_output("lang", {"language": "Greek", "confidence": 0.99}),
        complexity_output=_dummy_output("cpx", {"complexity": "simple", "confidence": 0.9}),
        direct_output=_dummy_output("dir", {"is_direct": True, "confidence": 0.9}),
        web_output=_dummy_output("web", {"needs_search": False, "confidence": 0.1}),
        method_output=_dummy_output("mth", {"category": "E", "confidence": 0.4}),
    )
    assert ctx.language == "Greek"
    assert ctx.complexity == "simple"


def test_hyper_context_to_dict_keys():
    ctx = HyperContext(
        problem="test",
        lang_output=_dummy_output("lang", {"language": "English", "confidence": 0.9}),
        complexity_output=_dummy_output("cpx", {"complexity": "complex", "confidence": 0.9}),
        direct_output=_dummy_output("dir", {"is_direct": False, "confidence": 0.1}),
        web_output=_dummy_output("web", {"needs_search": True, "confidence": 0.8}),
        method_output=_dummy_output("mth", {"category": "G", "confidence": 0.75}),
    )
    d = ctx.to_dict()
    assert "language" in d
    assert "complexity" in d
    assert "direct_signals" in d
    assert "web_signals" in d
    assert "method_signals" in d


# ── Routing role: the model resolved must be the model called ─────────


@pytest.mark.asyncio
async def test_sub_agents_call_the_role_they_resolve():
    """Every sub-agent must call role="hypergate_subagent", not "primary".

    Regression: _llm_call used to resolve "hypergate_subagent" purely to sniff
    the provider, then issue the call with role="primary". ProviderRouter.resolve
    consults routing_table[role] first and only falls back to self.primary, so
    the model that actually answered was whichever one the preset had put in the
    primary slot -- grok-4.5 for 45 of the 49 presets, and a different model
    again for the four that declare routing["primary"] themselves. Nothing in
    the response revealed which had run.
    """
    seen_roles: list[str] = []

    async def recording_call(role, system_prompt, user_prompt, **kwargs):
        seen_roles.append(role)
        return _j(language="English", confidence=0.9), {
            "input_tokens": 10, "output_tokens": 5, "model": "fake-model",
        }

    router = MagicMock()
    router.get.return_value = FakeProvider()
    router.call = recording_call

    for agent_cls in (
        LanguageDetectorSubAgent, ComplexityEstimatorSubAgent, DirectDetectorSubAgent,
        WebSearchDetectorSubAgent, MethodClassifierSubAgent, TieBreakerSubAgent,
    ):
        agent = agent_cls()
        agent._cache.clear()
        await agent.execute(
            SubAgentInput(problem=f"probe for {agent_cls.__name__}", agent_name="probe"),
            router,
        )

    assert seen_roles, "no sub-agent issued an LLM call"
    assert set(seen_roles) == {"hypergate_subagent"}, (
        f"sub-agents called roles {sorted(set(seen_roles))}; all must use "
        f"BaseSubAgent.ROLE so the resolved provider is the one that answers"
    )


@pytest.mark.asyncio
async def test_temperature_is_left_to_the_provider():
    """_llm_call must always pass temperature and never sniff the model itself.

    The removed sniff inspected router.get(ROLE) and then called a *different*
    role, so on any fallback it gated on the wrong model. OpenAICompatibleProvider
    already drops temperature per-model in complete(), against the model it is
    about to call, which is the only place that can be correct.
    """
    seen: dict[str, Any] = {}

    async def recording_call(role, system_prompt, user_prompt, **kwargs):
        seen.update(kwargs)
        return _j(language="English", confidence=0.9), {
            "input_tokens": 10, "output_tokens": 5, "model": "fake-model",
        }

    router = MagicMock()
    # An OpenAI model here used to make the sniff suppress temperature.
    router.get.return_value = FakeProvider(model="openai/gpt-4o-mini")
    router.call = recording_call

    agent = LanguageDetectorSubAgent()
    agent._cache.clear()
    await agent.execute(
        SubAgentInput(problem="temperature probe", agent_name="probe"), router
    )

    assert "temperature" in seen, "temperature must reach the router unconditionally"
    assert seen["temperature"] == LanguageDetectorSubAgent.TEMPERATURE
    assert seen["timeout_seconds"] == LanguageDetectorSubAgent.TIMEOUT_SECONDS


def test_hypergate_router_gives_the_subagent_role_its_own_fallback():
    """fallback_routing must name hypergate_subagent explicitly.

    _resolve_fallback only consults fallback_table["primary"] when the failing
    provider IS the router's primary. For any other role it falls through to the
    primary provider itself -- so without this entry, a failing sub-agent would
    retry on the router's primary, which is exactly the slow model the
    sub-agent role exists to avoid.
    """
    from reasoner.application.services.gate_service import build_hypergate_router
    from reasoner.infrastructure.llm.registry import build_provider
    from reasoner.infrastructure.llm.router import ProviderRouter

    base = ProviderRouter(primary=build_provider("qwen3.5-flash"))
    gate_router = build_hypergate_router(base)

    assert "hypergate_subagent" in gate_router.routing_table
    assert "hypergate_subagent" in gate_router.fallback_table, (
        "sub-agent role has no explicit fallback; it would silently inherit "
        "the router's primary provider"
    )

    assigned = gate_router.resolve("hypergate_subagent")
    fb = gate_router._resolve_fallback("hypergate_subagent", assigned)
    assert fb is not None, "sub-agent role resolved no fallback at all"
    assert fb.model != assigned.model
    assert fb.model != gate_router.resolve_primary().model, (
        "sub-agent fallback is the router primary -- the slow path it must avoid"
    )
