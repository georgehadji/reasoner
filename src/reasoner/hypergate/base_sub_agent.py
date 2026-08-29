"""
BaseSubAgent — abstract base class every HyperGate sub-agent must extend.

Each sub-agent has:
- ONE job expressed as a narrow system prompt
- Its own class-level LRU cache (FIFO eviction)
- A single public method: execute(inp, router) → SubAgentOutput
- Graceful error handling: exceptions become SubAgentOutput with error set
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from reasoner.core.constants import (
    HYPERGATE_CACHE_SIZE,
    HYPERGATE_METHOD_THRESHOLD,
    HYPERGATE_TIMEOUT_SECONDS,
)
from reasoner.hypergate.models import SubAgentInput, SubAgentOutput
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.utils.json_safe import JSONDepthExceededError, safe_json_loads

logger = logging.getLogger(__name__)


class BaseSubAgent(ABC):
    """One job. One cache. One execute() call."""

    AGENT_NAME: str = "base"
    # The routing role these agents run on, mirroring subagents/base.py's ROLE.
    # Declaring it is the point: sub-agents previously *resolved* this role to
    # inspect the provider and then called role="primary", so which model they
    # actually ran on was whatever the preset had put in the primary slot, and
    # the two could differ without anything surfacing it.
    ROLE: str = "hypergate_subagent"
    MAX_TOKENS: int = 128
    TEMPERATURE: float = 0.0
    TIMEOUT_SECONDS: float = HYPERGATE_TIMEOUT_SECONDS

    _MAX_CACHE: int = HYPERGATE_CACHE_SIZE

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._cache = {}  # type: ignore
        return instance

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    def _system_prompt(self) -> str:
        """Return the focused system prompt for this sub-agent's single task."""

    @abstractmethod
    def _parse_result(self, raw: str) -> dict[str, Any]:
        """
        Parse the LLM's raw text into a structured dict.
        Must always return a dict even on partial responses.
        """

    # ── Public API ────────────────────────────────────────────────────

    async def execute(self, inp: SubAgentInput, router: ProviderRouter) -> SubAgentOutput:
        """Run the sub-agent; returns SubAgentOutput (never raises)."""
        cache_key = self._cache_key(inp.problem)
        if cached := self._cache.get(cache_key):
            logger.debug("[%s] cache hit", self.AGENT_NAME)
            return cached

        t0 = time.monotonic()
        try:
            raw, meta = await self._llm_call(inp, router)
            result = self._parse_result(raw)
            confidence = float(result.get("confidence", 0.0))
            reasoning = str(result.get("rationale", result.get("reasoning", "")))
            out = SubAgentOutput(
                agent_name=self.AGENT_NAME,
                result=result,
                confidence=confidence,
                reasoning=reasoning,
                tokens_in=meta.get("input_tokens", 0),
                tokens_out=meta.get("output_tokens", 0),
                model=meta.get("model", "unknown"),
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            logger.warning("[%s] failed: %s", self.AGENT_NAME, exc)
            out = SubAgentOutput(
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

        # Only cache clean, sufficiently confident results.
        if out.error is None and out.confidence >= HYPERGATE_METHOD_THRESHOLD:
            self._cache[cache_key] = out
            if len(self._cache) > self._MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))

        return out

    # ── Helpers ───────────────────────────────────────────────────────

    def _cache_key(self, problem: str) -> str:
        return hashlib.sha256(f"{self.AGENT_NAME}:{problem}".encode()).hexdigest()

    async def _llm_call(
        self, inp: SubAgentInput, router: ProviderRouter
    ) -> tuple[str, dict[str, Any]]:
        user_prompt = inp.problem
        if inp.context:
            # TieBreaker passes Phase-1 context; inject it as a JSON suffix.
            user_prompt = (
                f"{inp.problem}\n\n"
                f"[Phase-1 analysis context]\n{json.dumps(inp.context, ensure_ascii=False, indent=2)}"
            )

        # temperature is passed unconditionally. There used to be an is_openai
        # prefix sniff here that suppressed it, which was wrong three ways: it
        # inspected the provider resolved for ROLE while the call went to
        # role="primary", so it read one model and gated another; it duplicated
        # OpenAICompatibleProvider._FIXED_TEMPERATURE_MARKERS incompletely
        # (missing claude-opus, claude-fable, pareto-code); and it was redundant,
        # because the provider already drops temperature per-model in complete()
        # and stream_complete() using the model it is actually about to call.

        # NOTE: deliberately NOT wrapped in harden_system_prompt(), unlike the
        # other two LLM chokepoints (flows/services.call_llm, subagents/base).
        # HyperGate sub-agents see only the already-sanitised problem, never
        # scraped pages, stored memory, or another model's prose, and they emit
        # opaque-letter classifications with no free-text passthrough — so there
        # is no channel for propagating content to ride. Five of these run in
        # parallel on every single request, so the ~120-token preamble would be
        # real added latency and cost for no exposure. Re-adding it needs a
        # reason; see docs/MIND_VIRUS_IMPLEMENTATION_PLAN.md WP1.3.
        result = await router.call(
            role=self.ROLE,
            system_prompt=self._system_prompt(),
            user_prompt=user_prompt,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
            timeout_seconds=self.TIMEOUT_SECONDS,
        )
        from reasoner.infrastructure.llm.ports import DegradedLLMResponse
        if isinstance(result, DegradedLLMResponse):
            raise RuntimeError(result.error)
        return result

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract the first valid JSON object from raw LLM text."""
        # Strip fenced code blocks first, then fall through to raw scan.
        fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
        if fence:
            try:
                return safe_json_loads(fence.group(1), max_depth=50)
            except (json.JSONDecodeError, JSONDepthExceededError):
                pass
        # Use raw_decode to find the first syntactically complete JSON object,
        # correctly handling nested braces that non-greedy regex would truncate.
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch == "{":
                try:
                    obj, _ = decoder.raw_decode(text, i)
                    # Validate depth before returning
                    safe_json_loads(json.dumps(obj), max_depth=50)
                    return obj  # type: ignore[return-value]
                except (json.JSONDecodeError, JSONDepthExceededError):
                    continue
        raise ValueError(f"No JSON found in: {text[:200]!r}")
