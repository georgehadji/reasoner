"""
Unit tests for the HyperGate sub-agent system.

Uses a FakeRouter that returns configurable JSON per router.call() invocation so
every test is deterministic and offline.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.application.services.gate_service import (
    _HYPERGATE_ROLE_FALLBACKS,
    _HYPERGATE_ROLE_MODELS,
)
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

# The five that HyperGateAgent._run_phase1 fires concurrently via
# asyncio.gather, in that order, and the tie-breaker that follows them.
_PHASE1_SUB_AGENTS = (
    LanguageDetectorSubAgent,
    ComplexityEstimatorSubAgent,
    DirectDetectorSubAgent,
    WebSearchDetectorSubAgent,
    MethodClassifierSubAgent,
)
_GATE_SUB_AGENTS = (*_PHASE1_SUB_AGENTS, TieBreakerSubAgent)

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
    """Every sub-agent must call its own ROLE, not "primary".

    Regression: _llm_call used to resolve the sub-agent role purely to sniff
    the provider, then issue the call with role="primary". ProviderRouter.resolve
    consults routing_table[role] first and only falls back to self.primary, so
    the model that actually answered was whichever one the preset had put in the
    primary slot -- grok-4.5 for 45 of the 49 presets, and a different model
    again for the four that declare routing["primary"] themselves. Nothing in
    the response revealed which had run.

    Since W4 the roles are per-agent, so this also pins the mapping: an agent
    calling a role other than its own would silently take another agent's model.
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

    for agent_cls in _GATE_SUB_AGENTS:
        agent = agent_cls()
        agent._cache.clear()
        seen_roles.clear()
        await agent.execute(
            SubAgentInput(problem=f"probe for {agent_cls.__name__}", agent_name="probe"),
            router,
        )
        assert seen_roles == [agent_cls.ROLE], (
            f"{agent_cls.__name__} called roles {seen_roles}; it must use its own "
            f"ROLE ({agent_cls.ROLE!r}) so the resolved provider is the one that answers"
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


def _gate_router():
    """A gate router built off an arbitrary preset router, as production does."""
    from reasoner.application.services.gate_service import build_hypergate_router
    from reasoner.infrastructure.llm.registry import build_provider
    from reasoner.infrastructure.llm.router import ProviderRouter

    # qwen3.5-flash is deliberately a model the gate must NOT end up using:
    # it is the one that returns -1.0000000000000002e+308 for every field.
    return build_hypergate_router(ProviderRouter(primary=build_provider("qwen3.5-flash")))


def test_every_gate_sub_agent_declares_a_known_role():
    """A new sub-agent cannot ship without a routing role the domain accepts.

    PipelinePreset.__post_init__ rejects any routing key outside
    _KNOWN_ROUTING_ROLES, so a role missing from that frozenset makes every
    preset declaring it raise at construction -- which is how
    "hypergate_subagent" itself sat unlisted until W4.
    """
    from reasoner.domain.preset_core import _KNOWN_ROUTING_ROLES

    for agent_cls in _GATE_SUB_AGENTS:
        assert agent_cls.ROLE in _KNOWN_ROUTING_ROLES, (
            f"{agent_cls.__name__}.ROLE = {agent_cls.ROLE!r} is not in "
            f"_KNOWN_ROUTING_ROLES; a preset naming it would raise"
        )


def test_each_gate_sub_agent_has_its_own_role():
    """The five Phase-1 agents must not share a role.

    Sharing one role is what made asyncio.gather fire five concurrent calls at
    a single upstream endpoint: probed alone the model answered in 1.47-1.92s,
    in the running app it averaged 5.86s.
    """
    roles = [cls.ROLE for cls in _PHASE1_SUB_AGENTS]
    assert len(set(roles)) == len(roles), f"Phase-1 agents share a role: {roles}"


@pytest.mark.parametrize("role", sorted(_HYPERGATE_ROLE_MODELS))
def test_every_gate_role_has_a_usable_explicit_fallback(role):
    """fallback_routing must name every gate role explicitly.

    _resolve_fallback only consults fallback_table["primary"] when the failing
    provider IS the router's primary. For any other role it falls through to the
    primary provider itself -- so without an entry, a failing sub-agent retries
    on the router's primary, which is neither cross-vendor nor necessarily
    capable of that agent's job.
    """
    gate_router = _gate_router()

    assert role in gate_router.routing_table
    assert role in gate_router.fallback_table, (
        f"{role} has no explicit fallback; it would silently inherit the "
        f"router's primary provider"
    )

    assigned = gate_router.resolve(role)
    fb = gate_router._resolve_fallback(role, assigned)
    assert fb is not None, f"{role} resolved no fallback at all"
    assert fb.model != assigned.model
    assert fb.model != gate_router.resolve_primary().model, (
        f"{role}'s fallback is the router primary -- the default an absent "
        f"entry already gives you, so the entry buys nothing"
    )


@pytest.mark.parametrize("role", sorted(_HYPERGATE_ROLE_MODELS))
def test_every_gate_role_falls_back_across_vendors(role):
    """A fallback sharing a vendor with the model that just failed is not one.

    Same cross-lab convention the presets follow: an upstream outage or rate
    limit takes out every model behind it, so the retry has to leave the vendor.
    """
    from reasoner.core.ports.model_registry_port import get_model_registry_port

    registry = get_model_registry_port()
    primary_vendor = registry.vendor_of(_HYPERGATE_ROLE_MODELS[role])
    fallback_vendor = registry.vendor_of(_HYPERGATE_ROLE_FALLBACKS[role])
    assert primary_vendor != fallback_vendor, (
        f"{role} falls back from {primary_vendor} to itself"
    )


def test_concurrent_gate_roles_resolve_to_distinct_models():
    """No two Phase-1 roles may share a served model.

    This is the invariant W4 exists to establish, and the same one
    validate_presets.py Invariant C enforces for presets. Roles that never run
    at the same time are exempt and are listed explicitly rather than inferred:
    hypergate_tiebreak runs only after Phase 1 has returned, and
    hypergate_subagent is reached only by ImageModelSelector, invoked on its own
    from api/routes/images.py.
    """
    gate_router = _gate_router()
    concurrent = [cls.ROLE for cls in _PHASE1_SUB_AGENTS]

    resolved = {role: gate_router.resolve(role).model for role in concurrent}
    assert len(set(resolved.values())) == len(resolved), (
        f"Phase-1 roles collide on a served model, so they will contend on one "
        f"upstream endpoint exactly as before W4: {resolved}"
    )


# ── decide_route total budget (W3b) ────────────────────────────────────


@pytest.mark.asyncio
async def test_decide_route_enforces_total_budget():
    """decide_route must not block past HYPERGATE_TOTAL_BUDGET_SECONDS.

    Regression: /api/gate used to await gate.decide() with no ceiling at all --
    measured 30,189ms on one complex prompt before this. On expiry it must
    return the same conservative verdict the pipeline preflight already
    produces on its own timeout (action=pipeline, low confidence,
    needs_confirmation=True), not hang and not raise past the caller.

    A warm-up call precedes the timed one. PresetService.build_router() pays a
    one-time lazy-init cost on its first call in a process (measured 2-2.9s
    here; near-zero on every call after) that is unrelated to the gate LLM
    call this budget bounds -- a real server pays it once at startup or on its
    first request, not per request. Timing cold would measure that warm-up
    cost, not asyncio.wait_for's enforcement.
    """
    import time
    from unittest.mock import patch

    from reasoner.application.services import gate_service
    from reasoner.hypergate import GateDecision

    async def _fast(problem):
        return GateDecision(action="direct", confidence=0.95, reasoning="warm-up")

    async def _stalls_past_budget(problem):
        await asyncio.sleep(gate_service.HYPERGATE_TOTAL_BUDGET_SECONDS + 5)

    with patch("reasoner.application.services.gate_service.HyperGateAgent") as mock_cls:
        mock_cls.return_value.decide = _fast
        await gate_service.decide_route("warm up the preset registry", "auto-budget")

    with patch("reasoner.application.services.gate_service.HyperGateAgent") as mock_cls:
        mock_cls.return_value.decide = _stalls_past_budget
        t0 = time.monotonic()
        result = await gate_service.decide_route("stalls forever", "auto-budget")
        elapsed = time.monotonic() - t0

    assert elapsed < gate_service.HYPERGATE_TOTAL_BUDGET_SECONDS + 1.0, (
        f"decide_route took {elapsed:.1f}s, budget is "
        f"{gate_service.HYPERGATE_TOTAL_BUDGET_SECONDS}s"
    )
    assert result["action"] == "pipeline"
    assert result["confidence"] == 0.0
    assert result["needs_confirmation"] is True
    assert "budget" in result["reasoning"].lower()


@pytest.mark.asyncio
async def test_decide_route_happy_path_unaffected_by_budget_wrapper():
    """A gate decision that returns well within budget must pass through untouched."""
    from unittest.mock import patch

    from reasoner.application.services import gate_service
    from reasoner.hypergate import GateDecision

    fast_decision = GateDecision(
        action="direct", confidence=0.95, reasoning="Detected simple factual lookup"
    )

    async def _fast(problem):
        return fast_decision

    with patch("reasoner.application.services.gate_service.HyperGateAgent") as mock_cls:
        mock_cls.return_value.decide = _fast
        result = await gate_service.decide_route("What is the capital of France?", "auto-budget")

    assert result["action"] == "direct"
    assert result["confidence"] == 0.95
    assert result["needs_confirmation"] is False
