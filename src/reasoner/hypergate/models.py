"""
Data models for the HyperGate sub-agent communication protocol.

All models are frozen dataclasses — sub-agents receive immutable inputs and
return immutable outputs.  The HyperGateAgent assembles a HyperContext from
Phase 1 results and passes it (as a plain dict) to the TieBreakerSubAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SubAgentInput:
    """Sent by HyperGateAgent to each sub-agent."""
    problem: str
    agent_name: str
    # Populated only for Phase-2 TieBreaker; empty for Phase-1 agents.
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubAgentOutput:
    """Returned by every sub-agent back to HyperGateAgent."""
    agent_name: str
    result: dict[str, Any]   # agent-specific payload (see each sub-agent for schema)
    confidence: float         # 0.0–1.0 extracted from result for quick access
    reasoning: str
    tokens_in: int
    tokens_out: int
    model: str
    duration_ms: float
    error: str | None = None  # non-None = graceful failure; hyperagent can still proceed


@dataclass
class HyperContext:
    """
    Assembled by HyperGateAgent after Phase 1 completes.
    Passed (as to_dict()) to TieBreakerSubAgent when synthesis is ambiguous.
    """
    problem: str
    lang_output: SubAgentOutput
    complexity_output: SubAgentOutput
    direct_output: SubAgentOutput
    web_output: SubAgentOutput
    method_output: SubAgentOutput

    # Convenience helpers — read from outputs with safe fallbacks
    @property
    def language(self) -> str:
        return self.lang_output.result.get("language", "English")

    @property
    def complexity(self) -> str:
        return self.complexity_output.result.get("complexity", "medium")

    def to_dict(self) -> dict[str, Any]:
        """Serialise for injection into TieBreakerSubAgent context.

        This dict becomes part of an LLM prompt, so every "method" key is
        dropped: MethodClassifier's result carries real method names (top pick
        and each candidate) for code downstream, and the TieBreaker must see its
        opaque "category" letters only (CLAUDE.md §5).
        """
        def _without_method_names(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: _without_method_names(v) for k, v in value.items() if k != "method"}
            if isinstance(value, list):
                return [_without_method_names(v) for v in value]
            return value

        def _safe(out: SubAgentOutput) -> dict[str, Any]:
            return {
                "result": _without_method_names(out.result),
                "confidence": out.confidence,
                "reasoning": out.reasoning,
                "error": out.error,
            }

        return {
            "language": self.language,
            "complexity": self.complexity,
            "lang_signals": _safe(self.lang_output),
            "complexity_signals": _safe(self.complexity_output),
            "direct_signals": _safe(self.direct_output),
            "web_signals": _safe(self.web_output),
            "method_signals": _safe(self.method_output),
        }
