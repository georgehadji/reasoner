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
# injected, and None means the feature is off. The only consumer today is the
# HyperGate shadow (hypergate/jev_shadow.py), which must never be the reason a
# request fails or slows down, so an absent port is the normal, safe state.
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
