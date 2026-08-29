"""
GateDecision — the routing verdict HyperGate produces: direct answer, live
pipeline, or a live web search.

The router that produces this decision is HyperGateAgent (hyperagent.py): five
focused sub-agents in parallel, synthesised with no extra LLM call. This module
used to also hold GateAgent, a single-LLM-call predecessor with its own
taxonomy and its own opaque-letter prompt. It was superseded and never
instantiated again after HyperGateAgent replaced it -- confirmed 2026-08-29 by
grepping every `GateAgent(` call site in src/ and tests/ and finding none
outside this file's own (now-deleted) class body. Deleted rather than fixed:
it carried the same role="primary" bug independently found and fixed in
HyperGateAgent's sub-agents (e241bb8), and a second category taxonomy that had
drifted from the live one in sub_agents/method_classifier.py -- this file's
"F" meant `iterative`, the live map's "F" means `jury`, and R/S/T/U were never
added here at all. A dead class with a stale taxonomy is a trap for whoever
next debugs a routing bug and finds two answers to "what does F mean".

Security principles carried forward to HyperGateAgent:
- Opaque taxonomy: real method names are never exposed to the LLM prompt.
- Fail-safe: any error, timeout, or low-confidence result falls back to pipeline.
- Input is already sanitized by the time it reaches the gate.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GateDecision(BaseModel):
    action: Literal["direct", "pipeline", "web_search"]
    method: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
    complexity: str | None = None
    language: str | None = None
    augmentation_methods: list[str] | None = None
    alternatives: list[dict[str, Any]] | None = None
