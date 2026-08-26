"""
PhaseSubAgent — abstract base class for intra-phase focused reasoning agents.

Each sub-agent has:
- A single focused responsibility (one job)
- Access to PipelineState for context
- Content-based caching (keyed by hash of state-relevant fields)
- Automatic token/cost tracking via PipelineState mutation
- Graceful error handling (exceptions become PhaseSubAgentOutput with error set)

Intended for use within pipeline phases (Synthesis, Critique, Decomposition, etc.)
NOT for pre-flight routing (use HyperGate BaseSubAgent for that).
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from reasoner.core.constants import HYPERGATE_METHOD_THRESHOLD
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.subagents.models import PhaseSubAgentOutput

logger = logging.getLogger(__name__)


class PhaseSubAgent(ABC):
    """One focused reasoning task within a pipeline phase."""

    AGENT_NAME: str = "base"
    MAX_TOKENS: int = 1024
    TEMPERATURE: float = 0.3
    ROLE: str = "synthesis"
    TIMEOUT_SECONDS: float = 30.0

    _MAX_CACHE: int = 256

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._cache = {}  # type: ignore
        return instance

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) given current pipeline state."""

    @abstractmethod
    def _parse_result(self, raw: str) -> dict[str, Any]:
        """Parse LLM raw text into structured dict. Always returns a dict."""

    # ── Cache key generation ──────────────────────────────────────────

    def _cache_key(self, state: PipelineState) -> str:
        """Build a content-based cache key from state-relevant fields."""
        # Default: hash problem + agent name + preset
        # Subclasses can override for finer-grained keys.
        content = f"{self.AGENT_NAME}:{state.problem}:{state.preset_name or ''}"
        return hashlib.sha256(content.encode()).hexdigest()

    # ── Public API ────────────────────────────────────────────────────

    # Human-readable description of what this agent does (shown in UI)
    TASK_DESCRIPTION: str = ""

    async def execute(self, state: PipelineState, router: ProviderRouter) -> PhaseSubAgentOutput:
        """Run the sub-agent; returns PhaseSubAgentOutput (never raises)."""
        cache_key = self._cache_key(state)
        if cached := self._cache.get(cache_key):
            logger.debug("[%s] cache hit", self.AGENT_NAME)
            return cached

        # Emit agent_start event for real-time UI tracking
        from reasoner.application.services.event_emission_service import get_event_emitter
        _emitter = get_event_emitter()
        if _emitter:
            _emitter.append_pending_event({
            "type": "agent_start",
            "agent": self.AGENT_NAME,
            "role": self.ROLE,
            "task": self.TASK_DESCRIPTION or self.AGENT_NAME.replace("_", " ").title(),
        })

        t0 = time.monotonic()
        try:
            system_prompt, user_prompt = self._build_prompt(state)
            # Propagation resistance (docs/MIND_VIRUS_MITIGATION.md M1/M2).
            # Subagents reach the router directly instead of through
            # WorkflowServices.call_llm, so the hardening is applied here too:
            # enhancement subagents read scraped web content, critique subagents
            # read other models' output.
            from reasoner.phases._shared import harden_system_prompt

            raw, meta = await router.call(
                role=self.ROLE,
                system_prompt=harden_system_prompt(system_prompt),
                user_prompt=user_prompt,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                timeout_seconds=self.TIMEOUT_SECONDS,
            )
            from reasoner.infrastructure.llm.ports import DegradedLLMResponse
            if isinstance(raw, DegradedLLMResponse):
                raise RuntimeError(raw.error)
            result = self._parse_result(raw)
            confidence = float(result.get("confidence", 0.0))
            reasoning = str(result.get("rationale", result.get("reasoning", "")))
            out = PhaseSubAgentOutput(
                agent_name=self.AGENT_NAME,
                result=result,
                confidence=confidence,
                reasoning=reasoning,
                tokens_in=meta.get("input_tokens", 0),
                tokens_out=meta.get("output_tokens", 0),
                model=meta.get("model", "unknown"),
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )
            # Track costs in PipelineState
            self._track_usage(state, meta, out)
        except Exception as exc:
            logger.warning("[%s] failed: %s", self.AGENT_NAME, exc)
            out = PhaseSubAgentOutput(
                agent_name=self.AGENT_NAME,
                result={},
                confidence=0.0,
                reasoning="",
                tokens_in=0,
                tokens_out=0,
                model="unknown",
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
                error=str(exc),
            )

        logger.debug(
            "[%s] confidence=%.2f duration=%.0fms model=%s",
            self.AGENT_NAME,
            out.confidence,
            out.duration_ms,
            out.model,
        )

        # Emit agent_complete event
        if _emitter:
            _emitter.append_pending_event({
                "type": "agent_complete",
                "agent": self.AGENT_NAME,
                "duration_ms": out.duration_ms,
                "model": out.model,
                "error": out.error,
            })

        # Cache clean, confident results
        if out.error is None and out.confidence >= HYPERGATE_METHOD_THRESHOLD:
            self._cache[cache_key] = out
            if len(self._cache) > self._MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))

        return out

    # ── Helpers ───────────────────────────────────────────────────────

    def _track_usage(self, state: PipelineState, meta: dict[str, Any], out: PhaseSubAgentOutput) -> None:
        """Accumulate token usage and cost into PipelineState."""
        role = self.ROLE
        cost = meta.get("cost_usd", 0.0)
        state.total_cost_usd += cost

        if role not in state.phase_costs:
            state.phase_costs[role] = 0.0
        state.phase_costs[role] += cost

        tokens_in = meta.get("input_tokens", 0)
        tokens_out = meta.get("output_tokens", 0)

        if role not in state.detailed_token_usage:
            state.detailed_token_usage[role] = {"input": 0, "output": 0, "total": 0}
        state.detailed_token_usage[role]["input"] += tokens_in
        state.detailed_token_usage[role]["output"] += tokens_out
        state.detailed_token_usage[role]["total"] += tokens_in + tokens_out

        state.phase_models[role] = out.model

        # Track models under the current phase key so the API can report per-phase models
        phase_key = getattr(state, '_current_phase_key', None)
        if phase_key:
            if phase_key not in state.cost_state._phase_models_by_key:
                state.cost_state._phase_models_by_key[phase_key] = []
            if out.model and out.model not in state.cost_state._phase_models_by_key[phase_key]:
                state.cost_state._phase_models_by_key[phase_key].append(out.model)

        # Also track under agent-specific key for transparency
        agent_key = f"subagent:{self.AGENT_NAME}"
        if agent_key not in state.phase_tokens:
            state.phase_tokens[agent_key] = {"input": 0, "output": 0}
        state.phase_tokens[agent_key]["input"] += tokens_in
        state.phase_tokens[agent_key]["output"] += tokens_out
