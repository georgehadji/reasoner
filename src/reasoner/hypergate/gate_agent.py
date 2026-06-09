"""
Gate Agent — Lightweight pre-flight router that decides whether a user prompt
should receive a direct answer or be processed through the full Reasoner pipeline.

Security principles:
- Opaque taxonomy: real method names are never exposed to the LLM prompt.
- Fail-safe: any error, timeout, or low-confidence result falls back to pipeline.
- Input is already sanitized by the time it reaches the gate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Literal


from pydantic import BaseModel, Field

from reasoner.core.constants import (
    GATE_CONFIDENCE_THRESHOLD,
    GATE_MAX_TOKENS,
    GATE_TEMPERATURE,
    GATE_TIMEOUT_SECONDS,
)
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.utils.json_safe import safe_json_loads, JSONDepthExceededError

logger = logging.getLogger(__name__)


class GateDecision(BaseModel):
    action: Literal["direct", "pipeline", "web_search"]
    method: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
    complexity: str | None = None


# Internal opaque taxonomy. The LLM sees only the letters (A-L), never the real method names.
_TAXONOMY = {
    "A": ("direct", None),
    "B": ("pipeline", "debate"),
    "C": ("pipeline", "scientific"),
    "D": ("pipeline", "socratic"),
    "E": ("pipeline", "multi_perspective"),
    "F": ("pipeline", "iterative"),
    "G": ("pipeline", "research"),
    "H": ("pipeline", "pre_mortem"),
    "I": ("pipeline", "bayesian"),
    "J": ("pipeline", "dialectical"),
    "K": ("pipeline", "analogical"),
    "L": ("pipeline", "delphi"),
    "M": ("pipeline", "cove"),
    "N": ("pipeline", "sot"),
    "O": ("pipeline", "tot"),
    "P": ("pipeline", "pot"),
    "Q": ("pipeline", "self_discover"),
    "W": ("web_search", None),
}

_GATE_SYSTEM_PROMPT = (
    "You are a routing assistant. Your job is to read the user request and classify it into exactly one category.\n"
    "Categories:\n"
    "- A: simple factual, conversational, or creative request → answer directly\n"
    "- B: requires adversarial reasoning with conflicting viewpoints\n"
    "- C: requires scientific hypothesis generation and falsification\n"
    "- D: requires deep Socratic questioning\n"
    "- E: requires multi-faceted analysis with multiple perspectives\n"
    "- F: requires iterative refinement with memory\n"
    "- G: requires research with web search\n"
    "- H: requires pre-mortem risk analysis\n"
    "- I: requires Bayesian belief updating\n"
    "- J: requires dialectical synthesis\n"
    "- K: requires analogical reasoning\n"
    "- L: requires expert panel consensus (Delphi)\n"
    "- M: requires structured fact-checking and verification\n"
    "- N: requires parallel decomposition and assembly\n"
    "- O: requires sequential decision tree search\n"
    "- P: requires computational reasoning with code\n"
    "- Q: requires dynamic reasoning module composition\n"
    "- W: requires simple factual web search (current events, weather, sports scores, recent news)\n\n"
    "Output ONLY valid JSON with keys: 'category' (A-W), 'confidence' (0.0-1.0), 'reasoning' (one sentence).\n"
    "Do not include markdown formatting, explanations, or code fences."
)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from raw text."""
    # Try to find JSON inside a code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return safe_json_loads(fence_match.group(1), max_depth=50)
        except (json.JSONDecodeError, JSONDepthExceededError):
            pass
    # Otherwise look for the first bare JSON object
    bare_match = re.search(r"(\{.*?\})", text, re.DOTALL)
    if bare_match:
        try:
            return safe_json_loads(bare_match.group(1), max_depth=50)
        except (json.JSONDecodeError, JSONDepthExceededError):
            pass
    raise ValueError("No JSON object found in response")


class GateAgent:
    _MAX_CACHE_SIZE = 512

    def __init__(self, router: ProviderRouter) -> None:
        self.router = router
        self._cache: dict[str, GateDecision] = {}

    async def decide(self, problem: str) -> GateDecision:
        """Return a GateDecision. Any failure falls back to pipeline."""
        if not isinstance(problem, str):
            problem = str(problem)
        problem_hash = hashlib.sha256(problem.encode()).hexdigest()
        cached = self._cache.get(problem_hash)
        if cached is not None:
            logger.debug("GateAgent cache hit for problem_hash=%s...", problem_hash[:16])
            return cached

        # Very short prompts are usually direct conversational queries
        if len(problem.strip()) < 10:
            return GateDecision(action="direct", confidence=1.0, reasoning="Very short prompt, assumed direct")

        # OpenAI models (gpt-, o1, o3) do not accept temperature in this codebase.
        # Inspect the assigned provider and omit temperature if needed.
        provider = self.router.get("primary")
        model_name = getattr(provider, "model", "").lower()
        is_openai_model = any(model_name.startswith(p) for p in ("gpt-", "o1", "o3", "openai/"))

        call_kwargs: dict[str, Any] = {
            "max_tokens": GATE_MAX_TOKENS,
            "timeout_seconds": GATE_TIMEOUT_SECONDS,
        }
        if not is_openai_model:
            call_kwargs["temperature"] = GATE_TEMPERATURE
        else:
            logger.debug("GateAgent omitting temperature for OpenAI model %s", model_name)

        try:
            response, meta = await self.router.call(
                role="primary",
                system_prompt=_GATE_SYSTEM_PROMPT,
                user_prompt=problem,
                **call_kwargs,
            )
        except Exception as exc:
            logger.warning("GateAgent LLM call failed: %s. Falling back to pipeline.", exc)
            return GateDecision(
                action="pipeline",
                method="multi_perspective",
                confidence=0.0,
                reasoning="Gate LLM call failed, fallback to pipeline",
            )

        try:
            parsed = _extract_json(response)
            category = str(parsed.get("category", "")).strip().upper()
            confidence = float(parsed.get("confidence", 0.0))
            reasoning = str(parsed.get("reasoning", "")).strip()
        except Exception as exc:
            logger.warning("GateAgent failed to parse JSON (%s): %s. Falling back to pipeline.", exc, response)
            return GateDecision(
                action="pipeline",
                method="multi_perspective",
                confidence=0.0,
                reasoning="Gate JSON parse failed, fallback to pipeline",
            )

        if category not in _TAXONOMY:
            logger.warning("GateAgent returned unknown category '%s'. Falling back to pipeline.", category)
            return GateDecision(
                action="pipeline",
                method="multi_perspective",
                confidence=0.0,
                reasoning=f"Unknown category '{category}', fallback to pipeline",
            )

        action, method = _TAXONOMY[category]

        if action == "pipeline" and confidence < GATE_CONFIDENCE_THRESHOLD:
            logger.info(
                "GateAgent confidence too low (%.2f < %.2f). Falling back to pipeline.",
                confidence,
                GATE_CONFIDENCE_THRESHOLD,
            )
            return GateDecision(
                action="pipeline",
                method=method,
                confidence=confidence,
                reasoning=f"Low confidence ({confidence:.2f}), fallback to pipeline",
            )

        # Hash the problem for safe logging (no PII leakage)
        log_hash = problem_hash[:16]
        logger.info(
            "GateAgent decision: problem_hash=%s action=%s method=%s confidence=%.2f",
            log_hash,
            action,
            method,
            confidence,
        )

        decision = GateDecision(action=action, method=method, confidence=confidence, reasoning=reasoning)

        # Only cache clean, high-confidence successes (not fallbacks)
        if decision.confidence >= GATE_CONFIDENCE_THRESHOLD and (
            not decision.reasoning or "fallback" not in decision.reasoning.lower()
        ):
            self._cache[problem_hash] = decision
            if len(self._cache) > self._MAX_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))

        return decision
