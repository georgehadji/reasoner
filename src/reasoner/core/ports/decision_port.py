"""Port for typed-decision ("System One") models.

A System One model does not generate text. It takes a *state* (a string,
object, or array) and a set of typed questions -- choice, score, noul -- and
returns one constrained answer per question, with probabilities. TypeSafe's
jev, reached through OpenRouter, is the implementation today
(infrastructure/decision/systemone_adapter.py).

This is not an LLMPort: there is no prompt and no completion, so nothing here
goes through parsing.extract_json().

Implemented by:
  - infrastructure.decision.systemone_adapter.SystemOneAdapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

DecisionState = str | dict[str, Any] | list[str]


@dataclass(frozen=True)
class DecisionResult:
    # Question key -> the model's typed answer, as returned. A choice carries
    # "choice", "probabilities", "confidence"; a score "score", "probabilities",
    # "confidence"; a noul "noul" (P(yes), 0..1).
    answers: dict[str, dict[str, Any]]
    # The served model, which may be a dated snapshot of the one requested
    # (typesafe/jev-1.13 resolves to typesafe/jev-1.13-20260917).
    model: str
    cost_usd: float | None = None


@runtime_checkable
class DecisionPort(Protocol):
    async def decide(
        self,
        state: DecisionState,
        questions: dict[str, dict[str, Any]],
    ) -> DecisionResult: ...


# ── Dependency injection ─────────────────────────────────────────────────
# Mirrors shared_cache_port: the getter returns None when nothing has been
# injected, and None means the feature is off. The only consumer today is
# HyperGate (hypergate/jev_router.py), whose LLM sub-agents route whenever there
# is no port, so an absent port is a normal, safe state -- never an error.
_DECISION_PORT: DecisionPort | None = None


def set_decision_port(port: DecisionPort | None) -> None:
    """Inject the decision adapter. Called once at startup, and only when the
    feature using it is enabled. Accepts None so a test can restore the
    uninjected state."""
    global _DECISION_PORT
    _DECISION_PORT = port


def get_decision_port() -> DecisionPort | None:
    """Return the injected port, or None. Callers MUST treat None as "off"."""
    return _DECISION_PORT


# One switch for every jev call site (HyperGate routing, the iterative-critique
# critic): "active" lets jev decide, "shadow" runs it beside the LLM and logs
# both, "off" never calls it. See settings.JEV_MODE.
JEV_MODES = ("off", "shadow", "active")


def jev_mode() -> str:
    """settings.JEV_MODE, or "off" for anything unrecognised -- a typo fails safe."""
    from reasoner.core.settings import settings  # lazy: settings validates env on import

    return settings.JEV_MODE if settings.JEV_MODE in JEV_MODES else "off"
