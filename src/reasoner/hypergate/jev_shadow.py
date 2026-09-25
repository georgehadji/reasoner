"""Jev shadow for HyperGate: measure a System One model on real traffic,
without letting it touch a single route.

For every fresh gate decision (cache hits are skipped), the same routing
questions HyperGate's Phase-1 sub-agents answer with four LLM calls are put to
jev in ONE call. Jev's verdict is logged beside the gate's as one JSON line
(`jev_shadow {...}`). Nothing is returned to the caller and nothing is awaited
on the request path.

Why shadow first: jev's routing accuracy on this taxonomy and the calibration
of its probabilities are both unmeasured -- TypeSafe publishes no calibration
evidence, and a 5-prompt probe cannot establish either. These logs are the
evidence a later decision to route on jev would need.

Safety properties, each covered by tests/test_jev_shadow.py:
  - Off unless a DecisionPort is injected (api/__init__.py does so only when
    settings.JEV_SHADOW_ENABLED). No port, no call, no task.
  - Never raises into, never blocks, never alters the gate decision.
  - Real method names never leave: the method question uses the classifier's
    opaque letters and descriptions (CLAUDE.md §5).
  - The log carries a hash of the problem, never its text.

Not asked: language. GateDecision.language is never populated, so there is no
gate verdict to compare jev's against.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from reasoner.core.constants import JEV_SHADOW_MAX_STATE_CHARS, JEV_SHADOW_TIMEOUT_SECONDS
from reasoner.core.ports.decision_port import DecisionPort, get_decision_port
from reasoner.hypergate.gate_agent import GateDecision
from reasoner.hypergate.hyperagent import _RESEARCH_INDICATORS
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


def interpret(answers: dict[str, dict[str, Any]], problem: str) -> dict[str, Any]:
    """Turn jev's typed answers into a route, by jev's own rule.

    Deliberately not HyperGate's thresholds (0.80 / 0.65 / 0.70): those were
    tuned against LLM-verbalised confidence, and applying them to jev's
    probabilities would be arbitrary. A plain 0.5 is jev's own majority call.
    The research-indicator override is shared: it is deterministic regex, not a
    model judgment, and the gate applies it to every problem.

    Search is checked BEFORE direct, the reverse of the gate's order. A question
    that needs live data cannot be answered directly however simple it looks,
    and at 0.5 the two overlap: on the 2026-09-25 probe, "what is the bitcoin
    price today" (in Greek) came back p_direct=0.65, p_search=0.98. The gate
    gets away with direct-first only because its 0.80 direct floor excludes 0.65.

    Raises on a malformed answer; run_shadow logs that as a failed shadow.
    """
    p_direct = float(answers["is_direct"]["noul"])
    p_search = float(answers["needs_search"]["noul"])
    score = float(answers["complexity"]["score"])
    complexity = _COMPLEXITY_LEVELS[min(2, max(0, round(score)))]
    method_answer = answers["method"]
    category = str(method_answer["choice"])
    research_override = any(p.search(problem) for p in _RESEARCH_INDICATORS)

    if p_search >= 0.5:
        action, method = "web_search", None
    elif p_direct >= 0.5 and complexity == "simple" and not research_override:
        action, method = "direct", None
    else:
        action, method = "pipeline", MethodClassifierSubAgent.resolve(category)[1]

    probabilities = method_answer.get("probabilities") or {}
    top3 = sorted(probabilities.items(), key=lambda kv: -float(kv[1]))[:3]
    return {
        "action": action,
        "method": method,
        "category": category,
        "complexity": complexity,
        "complexity_score": score,
        "p_direct": p_direct,
        "p_search": p_search,
        "method_confidence": method_answer.get("confidence"),
        "method_top3": top3,
        "research_override": research_override,
    }


async def run_shadow(
    port: DecisionPort, problem: str, decision: GateDecision
) -> dict[str, Any] | None:
    """Ask jev, log both verdicts, return the record. Never raises."""
    problem_sha = hashlib.sha256(problem.encode()).hexdigest()[:16]
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            port.decide(problem[:JEV_SHADOW_MAX_STATE_CHARS], QUESTIONS),
            timeout=JEV_SHADOW_TIMEOUT_SECONDS,
        )
        jev = interpret(result.answers, problem)
    except Exception as exc:  # noqa: BLE001 -- a shadow must never surface an error
        logger.warning(
            "jev_shadow failed problem_sha=%s: %s: %s", problem_sha, type(exc).__name__, exc
        )
        return None

    gate = {
        "action": decision.action,
        "method": decision.method,
        "confidence": decision.confidence,
        "complexity": decision.complexity,
    }
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
    """Start a shadow for *decision* in the background, if one is configured.

    Returns immediately. With no DecisionPort injected -- the default -- this is
    a no-op: no call, no task.
    """
    port = get_decision_port()
    if port is None:
        return
    task = asyncio.get_running_loop().create_task(run_shadow(port, problem, decision))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
