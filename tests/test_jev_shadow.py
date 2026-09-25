"""Jev shadow: a System One model measured beside HyperGate, never routing.

Offline throughout: the adapter runs against httpx.MockTransport, and the
shadow against a fake DecisionPort. The method-name leak check for jev's
question payload lives with the gate's own, in test_hypergate.py
(test_no_method_name_reaches_a_gate_llm), so one test covers every string
HyperGate sends to a model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import pytest

from reasoner.application.services.gate_service import run_gate_cached
from reasoner.core.ports.decision_port import DecisionResult, get_decision_port, set_decision_port
from reasoner.hypergate import GateDecision, jev_shadow
from reasoner.hypergate.hyperagent import _RESEARCH_INDICATORS
from reasoner.infrastructure.decision.systemone_adapter import SYSTEMONE_URL, SystemOneAdapter

_PROBLEM = "Should our 40-person startup migrate from a monolith to microservices this year?"


def _answers(p_direct=0.05, p_search=0.03, score=2.0, choice="B") -> dict[str, dict[str, Any]]:
    """The shape jev returned on the 2026-09-25 live probe."""
    return {
        "is_direct": {"type": "noul", "noul": p_direct},
        "needs_search": {"type": "noul", "noul": p_search},
        "complexity": {"type": "score", "score": score, "confidence": 1},
        "method": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: 0.7, "J": 0.2, "E": 0.1},
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
        return DecisionResult(answers=self.answers, model="typesafe/jev-1.13-20260917", cost_usd=6.9e-05)


@pytest.fixture(autouse=True)
def _no_port_leaks():
    set_decision_port(None)
    yield
    set_decision_port(None)


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

    result = await _adapter(handler).decide("state text", jev_shadow.QUESTIONS)

    assert seen["url"] == SYSTEMONE_URL
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {"model": "typesafe/jev-1.13", "state": "state text",
                            "questions": jev_shadow.QUESTIONS}
    assert result.model == "typesafe/jev-1.13-20260917"
    assert result.cost_usd == pytest.approx(6.9342e-05)
    assert result.answers["method"]["choice"] == "B"


@pytest.mark.asyncio
async def test_adapter_rejects_a_partial_answer_set():
    """A missing answer must fail loudly, never be read as a default verdict."""
    partial = {k: v for k, v in _answers().items() if k != "needs_search"}
    adapter = _adapter(lambda r: httpx.Response(200, json={"answers": partial}))
    with pytest.raises(ValueError, match="needs_search"):
        await adapter.decide("s", jev_shadow.QUESTIONS)


@pytest.mark.asyncio
async def test_adapter_raises_on_http_error():
    adapter = _adapter(lambda r: httpx.Response(429, json={"error": "rate limited"}))
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.decide("s", jev_shadow.QUESTIONS)


@pytest.mark.parametrize(
    ("enabled", "key", "injected"),
    [(False, "sk-x", False), (True, None, False), (True, "", False), (True, "sk-x", True)],
)
def test_inject_only_when_enabled_and_keyed(monkeypatch, enabled, key, injected):
    from reasoner.core.settings import settings
    from reasoner.infrastructure.decision import inject_decision_port

    monkeypatch.setattr(settings, "JEV_SHADOW_ENABLED", enabled)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", key)
    inject_decision_port()
    port = get_decision_port()
    assert (port is not None) is injected
    if injected:
        assert isinstance(port, SystemOneAdapter)


# ── interpret(): jev's own rule ───────────────────────────────────────


@pytest.mark.parametrize(
    ("answers", "problem", "action", "method"),
    [
        (_answers(p_direct=0.99, score=0.0), "Hi, how are you?", "direct", None),
        # Direct but not simple is not direct.
        (_answers(p_direct=0.99, score=2.0), "Hi, how are you?", "pipeline", "debate"),
        (_answers(p_direct=0.65, p_search=0.98, score=0.0, choice="G"),
         "What's the bitcoin price today?", "web_search", None),
        (_answers(choice="I"), _PROBLEM, "pipeline", "bayesian"),
        # Unknown letter resolves the way the classifier's does: E.
        (_answers(choice="Z"), _PROBLEM, "pipeline", "multi_perspective"),
    ],
)
def test_interpret_routes_by_jevs_own_answers(answers, problem, action, method):
    out = jev_shadow.interpret(answers, problem)
    assert (out["action"], out["method"]) == (action, method)


def test_interpret_applies_the_gates_research_override():
    """Shared with HyperGate: a research-indicator problem is never direct."""
    problem = "Write a research article with citations"
    assert any(rx.search(problem) for rx in _RESEARCH_INDICATORS)
    out = jev_shadow.interpret(_answers(p_direct=0.99, p_search=0.1, score=0.0), problem)
    assert out["research_override"] is True
    assert out["action"] == "pipeline"


def test_interpret_raises_on_a_malformed_answer():
    bad = _answers()
    del bad["method"]["choice"]
    with pytest.raises(KeyError):
        jev_shadow.interpret(bad, _PROBLEM)


# ── run_shadow(): logs, never raises, never leaks text ────────────────


@pytest.mark.asyncio
async def test_run_shadow_logs_both_verdicts_and_a_hash_not_the_text(caplog):
    port = FakePort()
    with caplog.at_level(logging.INFO, logger="reasoner.hypergate.jev_shadow"):
        record = await jev_shadow.run_shadow(port, _PROBLEM, _gate())

    assert record is not None
    assert record["agree_route"] is True  # both: pipeline / debate
    assert record["agree_complexity"] is True
    assert record["model"] == "typesafe/jev-1.13-20260917"
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("jev_shadow {"))
    logged = json.loads(line.removeprefix("jev_shadow "))
    assert logged["problem_sha"] == record["problem_sha"]
    assert _PROBLEM not in caplog.text
    assert "microservices" not in caplog.text


@pytest.mark.asyncio
async def test_run_shadow_records_disagreement():
    record = await jev_shadow.run_shadow(FakePort(_answers(choice="J")), _PROBLEM, _gate())
    assert record["agree_action"] is True
    assert record["agree_route"] is False
    assert record["jev"]["method"] == "dialectical"


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [RuntimeError("boom"), httpx.ConnectError("down"), ValueError("partial")])
async def test_run_shadow_swallows_every_failure(exc):
    assert await jev_shadow.run_shadow(FakePort(exc=exc), _PROBLEM, _gate()) is None


@pytest.mark.asyncio
async def test_run_shadow_times_out(monkeypatch):
    monkeypatch.setattr(jev_shadow, "JEV_SHADOW_TIMEOUT_SECONDS", 0.01)
    assert await jev_shadow.run_shadow(FakePort(delay=1.0), _PROBLEM, _gate()) is None


@pytest.mark.asyncio
async def test_run_shadow_caps_the_state_it_sends(monkeypatch):
    monkeypatch.setattr(jev_shadow, "JEV_SHADOW_MAX_STATE_CHARS", 10)
    port = FakePort()
    await jev_shadow.run_shadow(port, "x" * 50, _gate())
    assert port.calls[0][0] == "x" * 10


# ── schedule() and the gate: off by default, never in the way ─────────


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
async def test_off_by_default_no_port_no_task(no_cache):
    assert get_decision_port() is None
    decision = _gate()
    out = await run_gate_cached(_FakeGate(decision), _PROBLEM)
    assert out is decision
    assert not jev_shadow._PENDING


@pytest.mark.asyncio
async def test_gate_decision_is_returned_untouched_while_the_shadow_runs(no_cache):
    port = FakePort(_answers(choice="J"))  # jev disagrees
    set_decision_port(port)
    decision = _gate()
    before = decision.model_dump()

    out = await run_gate_cached(_FakeGate(decision), _PROBLEM)
    await asyncio.gather(*jev_shadow._PENDING)

    assert out is decision
    assert out.model_dump() == before
    assert len(port.calls) == 1


@pytest.mark.asyncio
async def test_a_failing_shadow_never_reaches_the_gate_caller(no_cache):
    set_decision_port(FakePort(exc=RuntimeError("jev down")))
    decision = _gate()
    out = await run_gate_cached(_FakeGate(decision), _PROBLEM)
    results = await asyncio.gather(*jev_shadow._PENDING, return_exceptions=True)
    assert out is decision
    assert results == [None]


@pytest.mark.asyncio
async def test_a_slow_shadow_adds_no_latency(no_cache):
    set_decision_port(FakePort(delay=0.5))
    loop = asyncio.get_running_loop()
    started = loop.time()
    await run_gate_cached(_FakeGate(_gate()), _PROBLEM)
    assert loop.time() - started < 0.1
    for task in list(jev_shadow._PENDING):
        task.cancel()
    await asyncio.gather(*jev_shadow._PENDING, return_exceptions=True)
