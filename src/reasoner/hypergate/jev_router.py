"""Jev in HyperGate: route with a System One model, LLM sub-agents as fallback.

HyperGate's Phase 1 asks four LLMs four typed questions (direct? web search?
how complex? which method?) and synthesises the answers, escalating to a
TieBreaker LLM when they conflict. TypeSafe's jev answers the same questions in
ONE call (~0.5s) with probabilities instead of self-reported confidence.

settings.JEV_MODE picks how much of that jev does:

  active  route() runs after HyperGate's regex fast paths. If jev's verdict
          clears the confidence gate (JEV_ACCEPT_* in constants_limits), it IS
          the decision and the LLM sub-agents never run. If jev fails, times
          out, or answers below the gate, the LLM sub-agents decide exactly as
          they do without jev. Every such decision is logged as
          `jev_route {...}`, including jev's rejected verdict beside the LLMs'
          answer -- the disagreement data on the hard cases.
  shadow  the LLM sub-agents route; schedule() puts the same questions to jev
          in the background and logs `jev_shadow {...}`. Changes nothing.
  off     jev is never called.

Any mode needs a DecisionPort (infrastructure/decision.inject_decision_port);
with none injected every mode behaves as off.

Invariants, each tested (tests/test_jev_router.py):
  - route() never raises: every failure is a fallback to the LLM sub-agents.
  - Real method names never leave: the method question uses the classifier's
    opaque letters, descriptions and disambiguation rules (CLAUDE.md §5).
  - Logs carry a hash of the problem, never its text.

Not asked: language. GateDecision.language is never populated and the pipeline
does not read HyperGate's language detector, so there is nothing to answer for.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from reasoner.core.constants import (
    JEV_ACCEPT_DIRECT,
    JEV_ACCEPT_METHOD,
    JEV_ACCEPT_SEARCH,
    JEV_ACTIVE_TIMEOUT_SECONDS,
    JEV_MAX_STATE_CHARS,
    JEV_SHADOW_TIMEOUT_SECONDS,
)
from reasoner.core.degrade import degraded
from reasoner.core.ports.decision_port import DecisionPort, get_decision_port, jev_mode
from reasoner.hypergate.gate_agent import GateDecision
from reasoner.hypergate.sub_agents.method_classifier import (
    _DESCRIPTIONS,
    _DISAMBIGUATION,
    MethodClassifierSubAgent,
)

logger = logging.getLogger(__name__)

_COMPLEXITY_LEVELS = ("simple", "medium", "complex")

# The Phase-1 jobs, restated as typed questions. Instructions paraphrase the
# sub-agents' system prompts minus their JSON-format boilerplate, which a
# System One model has no use for.
QUESTIONS: dict[str, dict[str, Any]] = {
    "is_direct": {
        "type": "noul",
        "instructions": (
            "Can this request be answered directly, without a multi-step reasoning pipeline? "
            "Yes for greetings, simple arithmetic, definitions, casual conversation, basic "
            "factual questions with a known answer, and creative writing (poems, stories, "
            "letters, speeches, scripts). No for analysis, strategy, research, structured "
            "reasoning, trade-off evaluation, professional judgment, or research-backed "
            "articles, essays and blog posts."
        ),
    },
    "needs_search": {
        "type": "noul",
        "instructions": (
            "Does this query need real-time or very recent information that only a live web "
            "search can provide -- current weather, live scores, today's news, stock or crypto "
            "prices, recent product releases, exchange rates, or anything from the last few "
            "days or weeks? No for general knowledge, history, analysis, strategy, coding help "
            "or explanations."
        ),
    },
    "complexity": {
        "type": "score",
        "instructions": "How much reasoning depth does the problem need?",
        "criteria": [
            "simple: a greeting, basic fact, trivial lookup, or creative writing a capable "
            "model answers directly without research",
            "medium: needs some analysis but not deep multi-step reasoning",
            "complex: structured multi-phase reasoning, trade-off analysis, or expert knowledge",
        ],
    },
    "method": {
        "type": "choice",
        "instructions": (
            "Which reasoning category best fits the problem? " + _DISAMBIGUATION
        ),
        # Opaque letter -> description, the classifier's own single source.
        "criteria": dict(_DESCRIPTIONS),
    },
}


def _research_override(problem: str) -> bool:
    # Imported here, not at module level: hyperagent imports this module, so a
    # top-level import back into hyperagent would be circular.
    from reasoner.hypergate.hyperagent import _RESEARCH_INDICATORS

    return any(p.search(problem) for p in _RESEARCH_INDICATORS)


def interpret(answers: dict[str, dict[str, Any]], problem: str) -> dict[str, Any]:
    """Turn jev's typed answers into a route, by jev's own rule.

    Deliberately not HyperGate's thresholds (0.80 / 0.65 / 0.70): those were
    tuned against LLM-verbalised confidence, and applying them to jev's
    probabilities would be arbitrary. A plain 0.5 is jev's own majority call;
    whether that call is trusted is gate_decision()'s job, not this one's.
    The research-indicator override is shared: it is deterministic regex, not a
    model judgment, and the gate applies it to every problem.

    Search is checked BEFORE direct, the reverse of the gate's order. A question
    that needs live data cannot be answered directly however simple it looks,
    and at 0.5 the two overlap: on the 2026-09-25 probe, "what is the bitcoin
    price today" (in Greek) came back p_direct=0.65, p_search=0.98. The gate
    gets away with direct-first only because its 0.80 direct floor excludes 0.65.

    Raises on a malformed answer; callers treat that as a failed call.
    """
    p_direct = float(answers["is_direct"]["noul"])
    p_search = float(answers["needs_search"]["noul"])
    score = float(answers["complexity"]["score"])
    complexity = _COMPLEXITY_LEVELS[min(2, max(0, round(score)))]
    method_answer = answers["method"]
    category = str(method_answer["choice"])
    research_override = _research_override(problem)

    if p_search >= 0.5:
        action, method = "web_search", None
    elif p_direct >= 0.5 and complexity == "simple" and not research_override:
        action, method = "direct", None
    else:
        action, method = "pipeline", MethodClassifierSubAgent.resolve(category)[1]

    probabilities = {k: float(v) for k, v in (method_answer.get("probabilities") or {}).items()}
    top3 = sorted(probabilities.items(), key=lambda kv: -kv[1])[:3]
    return {
        "action": action,
        "method": method,
        "category": category,
        "complexity": complexity,
        "complexity_score": score,
        "p_direct": p_direct,
        "p_search": p_search,
        "p_method": probabilities.get(category, 0.0),
        "method_confidence": method_answer.get("confidence"),
        "method_top3": top3,
        "research_override": research_override,
    }


def gate_decision(verdict: dict[str, Any], model: str) -> GateDecision | None:
    """jev's verdict as the route, or None when it is below the confidence gate.

    The probability that must clear the gate is the one the route rests on:
    P(search) for web_search, P(direct) for direct, and the top method letter's
    probability for pipeline. It also becomes GateDecision.confidence, so the
    gate's cache rule (>= 0.70) and decide_route's needs_confirmation read a
    probability rather than an LLM's self-report.
    """
    action = verdict["action"]
    if action == "web_search":
        p, floor = verdict["p_search"], JEV_ACCEPT_SEARCH
    elif action == "direct":
        p, floor = verdict["p_direct"], JEV_ACCEPT_DIRECT
    else:
        p, floor = verdict["p_method"], JEV_ACCEPT_METHOD
    if p < floor:
        return None

    alternatives = None
    if action == "pipeline":
        alternatives = [
            {
                "method": MethodClassifierSubAgent.resolve(letter)[1],
                "confidence": round(prob, 4),
                "rationale": f"jev probability {prob:.2f}",
            }
            for letter, prob in verdict["method_top3"]
            if letter != verdict["category"] and prob >= 0.05
        ] or None
    # Must never contain the word "fallback": gate_service._is_cacheable reads
    # it as a degraded verdict and refuses to cache.
    reasoning = f"jev ({model}): {action} at p={p:.2f}"
    return GateDecision(
        action=action,
        method=verdict["method"],
        confidence=min(1.0, max(0.0, p)),
        reasoning=reasoning,
        complexity=verdict["complexity"],
        alternatives=alternatives,
    )


@dataclass(frozen=True)
class JevAttempt:
    """What route() did. decision is set only when jev's verdict is the route."""

    reason: str  # "accepted" | "below_gate" | "timeout" | "error: <Type>" | "off"
    decision: GateDecision | None = None
    verdict: dict[str, Any] | None = None
    latency_ms: int | None = None
    model: str | None = None
    cost_usd: float | None = None


_OFF = JevAttempt(reason="off")


async def route(problem: str) -> JevAttempt:
    """Active mode: ask jev and decide whether its answer is the route.

    Never raises. Anything but an accepted verdict leaves decision None, and
    HyperGateAgent.decide then runs the LLM sub-agents as if jev were absent.
    """
    port = get_decision_port()
    if port is None or jev_mode() != "active":
        return _OFF
    started = time.perf_counter()

    def _elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    try:
        result = await asyncio.wait_for(
            port.decide(problem[:JEV_MAX_STATE_CHARS], QUESTIONS),
            timeout=JEV_ACTIVE_TIMEOUT_SECONDS,
        )
        verdict = interpret(result.answers, problem)
        decision = gate_decision(verdict, result.model)
    except TimeoutError:
        return JevAttempt(reason="timeout", latency_ms=_elapsed())
    except Exception as exc:
        # The LLM sub-agents take over either way; this keeps the cause.
        return degraded(
            "jev.route",
            JevAttempt(reason=f"error: {type(exc).__name__}", latency_ms=_elapsed()),
            exc=exc,
        )
    return JevAttempt(
        reason="accepted" if decision is not None else "below_gate",
        decision=decision,
        verdict=verdict,
        latency_ms=_elapsed(),
        model=result.model,
        cost_usd=result.cost_usd,
    )


def _brief(decision: GateDecision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "method": decision.method,
        "confidence": decision.confidence,
        "complexity": decision.complexity,
    }


def log_route(problem: str, attempt: JevAttempt, final: GateDecision) -> None:
    """One `jev_route {...}` line per active-mode decision. Never raises."""
    if attempt.reason == "off":
        return
    try:
        v = attempt.verdict
        record = {
            "problem_sha": hashlib.sha256(problem.encode()).hexdigest()[:16],
            "source": "jev" if attempt.decision is not None else "llm",
            "reason": attempt.reason,
            "final": _brief(final),
            "jev": v,
            # Only meaningful on a fallback: would jev have routed the same way?
            "agree_route": (
                (v["action"], v["method"]) == (final.action, final.method)
                if v is not None and attempt.decision is None
                else None
            ),
            "latency_ms": attempt.latency_ms,
            "model": attempt.model,
            "cost_usd": attempt.cost_usd,
        }
        logger.info("jev_route %s", json.dumps(record, sort_keys=True, default=str))
    except Exception as exc:
        degraded("jev.route_log", None, exc=exc)


# ── Shadow mode ─────────────────────────────────────────────────────────


async def run_shadow(
    port: DecisionPort, problem: str, decision: GateDecision
) -> dict[str, Any] | None:
    """Ask jev, log both verdicts, return the record. Never raises."""
    problem_sha = hashlib.sha256(problem.encode()).hexdigest()[:16]
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            port.decide(problem[:JEV_MAX_STATE_CHARS], QUESTIONS),
            timeout=JEV_SHADOW_TIMEOUT_SECONDS,
        )
        jev = interpret(result.answers, problem)
    except Exception as exc:
        logger.warning(
            "jev_shadow failed problem_sha=%s: %s: %s", problem_sha, type(exc).__name__, exc
        )
        return None

    gate = _brief(decision)
    record = {
        "problem_sha": problem_sha,
        "gate": gate,
        "jev": jev,
        "agree_action": gate["action"] == jev["action"],
        "agree_route": (gate["action"], gate["method"]) == (jev["action"], jev["method"]),
        "agree_complexity": gate["complexity"] == jev["complexity"] if gate["complexity"] else None,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "model": result.model,
        "cost_usd": result.cost_usd,
    }
    logger.info("jev_shadow %s", json.dumps(record, sort_keys=True, default=str))
    return record


# Strong references to in-flight shadows. asyncio keeps only weak references to
# tasks, so an unreferenced one can be garbage-collected mid-flight.
_PENDING: set[asyncio.Task[Any]] = set()


def schedule(problem: str, decision: GateDecision) -> None:
    """Shadow mode: start a background comparison for *decision*.

    Returns immediately. A no-op unless the mode is "shadow" and a port is
    injected -- in active mode jev has already been asked, inside decide().
    """
    port = get_decision_port()
    if port is None or jev_mode() != "shadow":
        return
    task = asyncio.get_running_loop().create_task(run_shadow(port, problem, decision))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
