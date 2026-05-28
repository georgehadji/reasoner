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
from reasoner.utils.json_safe import safe_json_loads, JSONDepthExceededError

logger = logging.getLogger(__name__)


class BaseSubAgent(ABC):
    """One job. One cache. One execute() call."""

    AGENT_NAME: str = "base"
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
        provider = router.get("primary")
        model_name = getattr(provider, "model", "").lower()
        is_openai = any(model_name.startswith(p) for p in ("gpt-", "o1", "o3", "openai/"))

        user_prompt = inp.problem
        if inp.context:
            # TieBreaker passes Phase-1 context; inject it as a JSON suffix.
            user_prompt = (
                f"{inp.problem}\n\n"
                f"[Phase-1 analysis context]\n{json.dumps(inp.context, ensure_ascii=False, indent=2)}"
            )

        kwargs: dict[str, Any] = {
            "max_tokens": self.MAX_TOKENS,
            "timeout_seconds": self.TIMEOUT_SECONDS,
        }
        if not is_openai:
            kwargs["temperature"] = self.TEMPERATURE

        result = await router.call(
            role="primary",
            system_prompt=self._system_prompt(),
            user_prompt=user_prompt,
            **kwargs,
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
