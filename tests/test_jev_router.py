"""Jev in HyperGate: routes in active mode with the LLM sub-agents as fallback,
logs beside them in shadow mode, and is never called when off.

Offline throughout: the adapter runs against httpx.MockTransport, jev against a
fake DecisionPort, and the LLM sub-agents against a call-counting fake router.
The method-name leak check for jev's question payload lives with the gate's own
in test_hypergate.py (test_no_method_name_reaches_a_gate_llm), so one test
covers every string HyperGate sends to a model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from reasoner.application.services.gate_service import _is_cacheable, run_gate_cached
from reasoner.core.ports.decision_port import DecisionResult, get_decision_port, set_decision_port
from reasoner.core.settings import settings
from reasoner.hypergate import GateDecision, HyperGateAgent, jev_router
from reasoner.hypergate.hyperagent import _RESEARCH_INDICATORS
from reasoner.infrastructure.decision.systemone_adapter import SYSTEMONE_URL, SystemOneAdapter

_PROBLEM = "Should our 40-person startup migrate from a monolith to microservices this year?"


def _answers(p_direct=0.05, p_search=0.03, score=2.0, choice="B", p_top=0.7) -> dict[str, Any]:
    """The shape jev returned on the 2026-09-25 live probe."""
    rest = [k for k in ("J", "E", "Q") if k != choice][:2]
    return {
        "is_direct": {"type": "noul", "noul": p_direct},
        "needs_search": {"type": "noul", "noul": p_search},
        "complexity": {"type": "score", "score": score, "confidence": 1},
        "method": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: p_top, rest[0]: (1 - p_top) * 0.7, rest[1]: (1 - p_top) * 0.3},
            "confidence": 0.67,
        },
    }


class FakePort:
    def __init__(self, answers=None, exc: BaseException | None = None, delay: float = 0.0):
        self.answers = answers if answers is not None else _answers()
        self.exc = exc
        self.delay = delay
        self.calls: list[tuple[Any, dict]] = []

    async def decide(self, state, questions):
        self.calls.append((state, questions))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return DecisionResult(
            answers=self.answers, model="typesafe/jev-1.13-20260917", cost_usd=6.9e-05
        )


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    set_decision_port(None)
    monkeypatch.setattr(settings, "JEV_MODE", "off")
    yield
    set_decision_port(None)


@pytest.fixture
def jev_mode(monkeypatch):
    def _set(mode: str, port: FakePort | None = None) -> FakePort | None:
        monkeypatch.setattr(settings, "JEV_MODE", mode)
        set_decision_port(port)
        return port

    return _set


def _gate(action="pipeline", method="debate", complexity="complex") -> GateDecision:
    return GateDecision(action=action, method=method, confidence=0.8, complexity=complexity)


# ── Adapter ───────────────────────────────────────────────────────────


def _adapter(handler) -> SystemOneAdapter:
    return SystemOneAdapter(
        "sk-test", "typesafe/jev-1.13", 5.0, referer="https://r", app_title="Reasoner",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_adapter_sends_the_systemone_contract_and_parses_the_reply():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "typesafe/jev-1.13-20260917",
            "answers": _answers(),
            "usage": {"input_tokens": 1651, "output_tokens": 280, "cost": 6.9342e-05},
        })

    result = await _adapter(handler).decide("state text", jev_router.QUESTIONS)

    assert seen["url"] == SYSTEMONE_URL
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {"model": "typesafe/jev-1.13", "state": "state text",
                            "questions": jev_router.QUESTIONS}
    assert result.model == "typesafe/jev-1.13-20260917"
    assert result.cost_usd == pytest.approx(6.9342e-05)
    assert result.answers["method"]["choice"] == "B"


@pytest.mark.asyncio
async def test_adapter_rejects_a_partial_answer_set():
    """A missing answer must fail loudly, never be read as a default verdict."""
    partial = {k: v for k, v in _answers().items() if k != "needs_search"}
    adapter = _adapter(lambda r: httpx.Response(200, json={"answers": partial}))
    with pytest.raises(ValueError, match="needs_search"):
        await adapter.decide("s", jev_router.QUESTIONS)


@pytest.mark.asyncio
async def test_adapter_raises_on_http_error():
    adapter = _adapter(lambda r: httpx.Response(429, json={"error": "rate limited"}))
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.decide("s", jev_router.QUESTIONS)


@pytest.mark.parametrize(
    ("mode", "key", "injected"),
    [
        ("off", "sk-x", False),
        ("typo", "sk-x", False),
        ("active", None, False),
        ("active", "", False),
        ("active", "sk-x", True),
        ("shadow", "sk-x", True),
    ],
)
def test_inject_only_for_a_jev_mode_with_a_key(monkeypatch, mode, key, injected):
    from reasoner.infrastructure.decision import inject_decision_port

    monkeypatch.setattr(settings, "JEV_MODE", mode)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", key)
    inject_decision_port()
    port = get_decision_port()
    assert (port is not None) is injected
    if injected:
        assert isinstance(port, SystemOneAdapter)


def test_an_unknown_mode_reads_as_off(monkeypatch):
    monkeypatch.setattr(settings, "JEV_MODE", "actve")
    assert jev_router.mode() == "off"


# ── interpret(): jev's own rule ───────────────────────────────────────


@pytest.mark.parametrize(
    ("answers", "problem", "action", "method"),
    [
        (_answers(p_direct=0.99, score=0.0), "Hi, how are you?", "direct", None),
        # Direct but not simple is not direct.
        (_answers(p_direct=0.99, score=2.0), "Hi, how are you?", "pipeline", "debate"),
        # The live-probe case: both high. Search wins -- live data can't be answered directly.
        (_answers(p_direct=0.65, p_search=0.98, score=0.0, choice="G"),
         "What's the bitcoin price today?", "web_search", None),
        (_answers(choice="I"), _PROBLEM, "pipeline", "bayesian"),
        (_answers(choice="U"), _PROBLEM, "pipeline", "iterative_critique"),
        # Unknown letter resolves the way the classifier's does: E.
        (_answers(choice="Z"), _PROBLEM, "pipeline", "multi_perspective"),
    ],
)
def test_interpret_routes_by_jevs_own_answers(answers, problem, action, method):
    out = jev_router.interpret(answers, problem)
    assert (out["action"], out["method"]) == (action, method)


def test_interpret_applies_the_gates_research_override():
    """Shared with HyperGate: a research-indicator problem is never direct."""
    problem = "Write a research article with citations"
    assert any(rx.search(problem) for rx in _RESEARCH_INDICATORS)
    out = jev_router.interpret(_answers(p_direct=0.99, p_search=0.1, score=0.0), problem)
    assert out["research_override"] is True
    assert out["action"] == "pipeline"


def test_interpret_raises_on_a_malformed_answer():
    bad = _answers()
    del bad["method"]["choice"]
    with pytest.raises(KeyError):
        jev_router.interpret(bad, _PROBLEM)


# ── gate_decision(): the confidence gate ──────────────────────────────


@pytest.mark.parametrize(
    ("answers", "accepted"),
    [
        (_answers(p_direct=0.90, score=0.0), True),
        (_answers(p_direct=0.79, score=0.0), False),  # below JEV_ACCEPT_DIRECT
        (_answers(p_search=0.90, choice="G"), True),
        (_answers(p_search=0.84, choice="G"), False),  # below JEV_ACCEPT_SEARCH
        (_answers(p_top=0.70), True),
        (_answers(p_top=0.55), False),  # below JEV_ACCEPT_METHOD
    ],
)
def test_the_gate_rests_on_the_probability_the_route_needs(answers, accepted):
    verdict = jev_router.interpret(answers, "Hi, how are you?" if answers["is_direct"]["noul"] > 0.5 else _PROBLEM)
    decision = jev_router.gate_decision(verdict, "m")
    assert (decision is not None) is accepted


def test_an_accepted_pipeline_decision_carries_real_alternatives_and_caches():
    verdict = jev_router.interpret(_answers(choice="B", p_top=0.75), _PROBLEM)
    d = jev_router.gate_decision(verdict, "typesafe/jev-1.13-20260917")
    assert (d.action, d.method) == ("pipeline", "debate")
    assert d.confidence == pytest.approx(0.75)
    assert [a["method"] for a in d.alternatives] == ["dialectical", "multi_perspective"]
    # gate_service caches confident verdicts unless reasoning says "fallback".
    assert "fallback" not in d.reasoning.lower()
    assert _is_cacheable(d)


# ── route(): active mode, never raises ────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["off", "shadow"])
async def test_route_does_nothing_outside_active_mode(jev_mode, mode):
    port = jev_mode(mode, FakePort())
    attempt = await jev_router.route(_PROBLEM)
    assert attempt.reason == "off" and attempt.decision is None
    assert port.calls == []


@pytest.mark.asyncio
async def test_route_does_nothing_without_a_port(jev_mode):
    jev_mode("active", None)
    assert (await jev_router.route(_PROBLEM)).reason == "off"


@pytest.mark.asyncio
async def test_route_accepts_a_confident_verdict(jev_mode):
    jev_mode("active", FakePort(_answers(choice="I", p_top=0.9)))
    attempt = await jev_router.route(_PROBLEM)
    assert attempt.reason == "accepted"
    assert (attempt.decision.action, attempt.decision.method) == ("pipeline", "bayesian")


@pytest.mark.asyncio
async def test_route_declines_below_the_gate_but_keeps_the_verdict(jev_mode):
    jev_mode("active", FakePort(_answers(p_top=0.4)))
    attempt = await jev_router.route(_PROBLEM)
    assert attempt.reason == "below_gate"
    assert attempt.decision is None
    assert attempt.verdict["method"] == "debate"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("port", "reason"),
    [
        (FakePort(exc=RuntimeError("down")), "error: RuntimeError"),
        (FakePort(exc=httpx.ConnectError("down")), "error: ConnectError"),
        (FakePort(answers={"is_direct": {"noul": 0.1}}), "error: KeyError"),  # malformed
    ],
)
async def test_route_turns_every_failure_into_a_fallback(jev_mode, port, reason):
    jev_mode("active", port)
    attempt = await jev_router.route(_PROBLEM)
    assert attempt.decision is None
    assert attempt.reason == reason


@pytest.mark.asyncio
async def test_route_times_out_into_a_fallback(jev_mode, monkeypatch):
    monkeypatch.setattr(jev_router, "JEV_ACTIVE_TIMEOUT_SECONDS", 0.01)
    jev_mode("active", FakePort(delay=1.0))
    attempt = await jev_router.route(_PROBLEM)
    assert (attempt.reason, attempt.decision) == ("timeout", None)


@pytest.mark.asyncio
async def test_route_caps_the_state_it_sends(jev_mode, monkeypatch):
    monkeypatch.setattr(jev_router, "JEV_MAX_STATE_CHARS", 10)
    port = jev_mode("active", FakePort())
    await jev_router.route("x" * 50)
    assert port.calls[0][0] == "x" * 10


# ── HyperGateAgent: jev first, LLM sub-agents as the fallback ─────────


def _llm_router(reply: str) -> Any:
    """A router whose every LLM call is counted and answers *reply*."""
    router = MagicMock()
    router.get.return_value = MagicMock(model="fake", last_input_tokens=1, last_output_tokens=1,
                                        last_cost_usd=0.0)
    router.calls = 0

    async def call(role, system_prompt, user_prompt, **kwargs):
        router.calls += 1
        return reply, {"input_tokens": 1, "output_tokens": 1, "model": "fake"}

    router.call = call
    return router


# Every Phase-1 sub-agent reads its own keys from this and defaults the rest:
# a confident method verdict of C (scientific), not direct, no search.
_LLM_REPLY = json.dumps({"category": "C", "confidence": 0.9, "rationale": "llm",
                         "is_direct": False, "needs_search": False, "complexity": "complex",
                         "language": "English"})


@pytest.mark.asyncio
async def test_an_accepted_jev_verdict_means_no_llm_sub_agent_runs(jev_mode, caplog):
    jev_mode("active", FakePort(_answers(choice="I", p_top=0.9)))
    router = _llm_router(_LLM_REPLY)
    with caplog.at_level(logging.INFO, logger="reasoner.hypergate.jev_router"):
        decision = await HyperGateAgent(router).decide(_PROBLEM + " (accepted)")
    assert (decision.action, decision.method) == ("pipeline", "bayesian")
    assert router.calls == 0
    record = _logged(caplog, "jev_route")
    assert (record["source"], record["reason"]) == ("jev", "accepted")


@pytest.mark.asyncio
async def test_below_the_gate_the_llm_sub_agents_decide_and_jev_is_logged(jev_mode, caplog):
    jev_mode("active", FakePort(_answers(choice="I", p_top=0.4)))
    router = _llm_router(_LLM_REPLY)
    with caplog.at_level(logging.INFO, logger="reasoner.hypergate.jev_router"):
        decision = await HyperGateAgent(router).decide(_PROBLEM + " (below gate)")
    assert (decision.action, decision.method) == ("pipeline", "scientific")
    assert router.calls >= 5
    record = _logged(caplog, "jev_route")
    assert (record["source"], record["reason"]) == ("llm", "below_gate")
    assert record["jev"]["method"] == "bayesian"
    assert record["agree_route"] is False


@pytest.mark.asyncio
async def test_a_failing_jev_leaves_the_llm_path_exactly_as_it_was(jev_mode):
    problem = _PROBLEM + " (jev down)"
    baseline = await HyperGateAgent(_llm_router(_LLM_REPLY)).decide(problem + " off")

    jev_mode("active", FakePort(exc=RuntimeError("jev down")))
    router = _llm_router(_LLM_REPLY)
    decision = await HyperGateAgent(router).decide(problem + " on")

    assert (decision.action, decision.method, decision.confidence) == (
        baseline.action, baseline.method, baseline.confidence
    )
    assert router.calls >= 5


@pytest.mark.asyncio
async def test_regex_fast_paths_still_come_before_jev(jev_mode):
    port = jev_mode("active", FakePort())
    decision = await HyperGateAgent(_llm_router(_LLM_REPLY)).decide("hi")
    assert decision.action == "direct"
    assert port.calls == []


@pytest.mark.asyncio
async def test_no_problem_text_in_any_log(jev_mode, caplog):
    jev_mode("active", FakePort(_answers(p_top=0.4)))
    with caplog.at_level(logging.DEBUG):
        await HyperGateAgent(_llm_router(_LLM_REPLY)).decide(_PROBLEM)
    jev_lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("jev_")]
    assert jev_lines
    assert not any("microservices" in line for line in jev_lines)


def _logged(caplog, prefix: str) -> dict[str, Any]:
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith(f"{prefix} {{"))
    return json.loads(line.removeprefix(f"{prefix} "))


# ── Shadow mode ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_shadow_logs_both_verdicts_and_a_hash_not_the_text(caplog):
    with caplog.at_level(logging.INFO, logger="reasoner.hypergate.jev_router"):
        record = await jev_router.run_shadow(FakePort(), _PROBLEM, _gate())
    assert record["agree_route"] is True  # both: pipeline / debate
    assert record["agree_complexity"] is True
    assert _logged(caplog, "jev_shadow")["problem_sha"] == record["problem_sha"]
    assert "microservices" not in caplog.text


@pytest.mark.asyncio
async def test_run_shadow_records_disagreement():
    record = await jev_router.run_shadow(FakePort(_answers(choice="J")), _PROBLEM, _gate())
    assert (record["agree_action"], record["agree_route"]) == (True, False)
    assert record["jev"]["method"] == "dialectical"


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [RuntimeError("boom"), httpx.ConnectError("down"), ValueError("x")])
async def test_run_shadow_swallows_every_failure(exc):
    assert await jev_router.run_shadow(FakePort(exc=exc), _PROBLEM, _gate()) is None


@pytest.mark.asyncio
async def test_run_shadow_times_out(monkeypatch):
    monkeypatch.setattr(jev_router, "JEV_SHADOW_TIMEOUT_SECONDS", 0.01)
    assert await jev_router.run_shadow(FakePort(delay=1.0), _PROBLEM, _gate()) is None


class _FakeGate:
    """Enough of HyperGateAgent for run_gate_cached."""

    def __init__(self, decision: GateDecision):
        self._decision = decision
        self.router = None

    async def decide(self, problem: str) -> GateDecision:
        return self._decision


@pytest.fixture
def no_cache(monkeypatch):
    import reasoner.application.services.gate_service as gs

    monkeypatch.setattr(gs, "get_shared_cache_port", lambda: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["off", "active"])
async def test_no_shadow_task_outside_shadow_mode(jev_mode, no_cache, mode):
    port = jev_mode(mode, FakePort())
    decision = _gate()
    assert await run_gate_cached(_FakeGate(decision), _PROBLEM) is decision
    assert not jev_router._PENDING
    assert port.calls == []  # _FakeGate never calls route(); schedule() must not either


@pytest.mark.asyncio
async def test_shadow_returns_the_gate_decision_untouched(jev_mode, no_cache):
    port = jev_mode("shadow", FakePort(_answers(choice="J")))  # jev disagrees
    decision = _gate()
    before = decision.model_dump()
    out = await run_gate_cached(_FakeGate(decision), _PROBLEM)
    await asyncio.gather(*jev_router._PENDING)
    assert out is decision and out.model_dump() == before
    assert len(port.calls) == 1


@pytest.mark.asyncio
async def test_a_slow_shadow_adds_no_latency(jev_mode, no_cache):
    jev_mode("shadow", FakePort(delay=0.5))
    loop = asyncio.get_running_loop()
    started = loop.time()
    await run_gate_cached(_FakeGate(_gate()), _PROBLEM)
    assert loop.time() - started < 0.1
    for task in list(jev_router._PENDING):
        task.cancel()
    await asyncio.gather(*jev_router._PENDING, return_exceptions=True)
