"""
HyperGateAgent — orchestrates 5 focused sub-agents in parallel (Phase 1) and
synthesises their results into a GateDecision without an extra LLM call.

When Phase-1 signals conflict or are all low-confidence, a TieBreakerSubAgent
runs as Phase 2 with the full HyperContext as input.

Drop-in replacement for GateAgent: same __init__ signature, same decide() output.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Literal

from reasoner.core.constants import (
    HYPERGATE_AMBIGUOUS_FLOOR,
    HYPERGATE_CACHE_SIZE,
    HYPERGATE_DIRECT_THRESHOLD,
    HYPERGATE_METHOD_THRESHOLD,
    HYPERGATE_WEB_THRESHOLD,
)
from reasoner.gate_agent import GateDecision
from reasoner.hypergate.models import HyperContext, SubAgentInput, SubAgentOutput
from reasoner.hypergate.sub_agents import (
    ComplexityEstimatorSubAgent,
    DirectDetectorSubAgent,
    LanguageDetectorSubAgent,
    MethodClassifierSubAgent,
    TieBreakerSubAgent,
    WebSearchDetectorSubAgent,
)
from reasoner.infrastructure.llm.router import ProviderRouter

# Fast-path patterns for pure creative-writing requests that should bypass the pipeline
# and go straight to direct answer (no search, no multi-phase reasoning).
# Deliberately excludes articles/essays/blog posts because those should route
# to the research-backed writing pipeline.
_CREATIVE_PATTERNS: list[re.Pattern[str]] = [
    # English — pure creative genres without topic indicators
    re.compile(r"\b(write|compose|draft|create|tell)\s+(me\s+)?(an?\s+)?(poem|story|narrative|letter|speech|script|joke|limerick|riddle)\b", re.I),
    re.compile(r"\b(tell\s+me\s+a\s+(story|joke)|make\s+up\s+a\s+(story|joke)|write\s+me\s+a\s+(poem|joke))\b", re.I),
    # Greek — pure creative genres
    re.compile(r"\b(γράψε|συνέθεσε|δημιούργησε|σχεδίασε|φτιάξε|πες)\s+(μου\s+)?(ένα\s+|μια\s+)?(ποίημα|ιστορία|λόγο|σενάριο|βιογραφικό|αφήγηση|ανέκδοτο|αινίγμα)\b", re.I),
    re.compile(r"\b(πες\s+μου|φτιάξε\s+μου|γράψε\s+μου)\s+(μια\s+)?(ιστορία|αφήγηση|ανέκδοτο)\b", re.I),
]

# Fast-path patterns for simple factual lookups that can be answered directly
# by a knowledge model (no web search or multi-phase reasoning needed).
_FACTUAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(what\s+is|who\s+is|where\s+is|when\s+is|how\s+many|define|explain)\s+(the\s+)?\w+", re.I),
    re.compile(r"\b(capital\s+of|president\s+of|invented)\s+\w+", re.I),
    re.compile(r"\b(ποιο\s+είναι|ποιος\s+είναι|πού\s+είναι|πότε\s+είναι|πόσα|πόσες|πόσους|ορίζω|εξήγησε)\s+(το\s+|η\s+|ο\s+)?\w+", re.I),
    re.compile(r"\b(πρωτεύουσα\s+της|πρόεδρος\s+της|εφεύρε)\s+\w+", re.I),
]

# Research indicators — used to detect if a writing request is research-backed.
_RESEARCH_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"\b(research\s+(article|paper|essay)|informative\s+(article|essay)|academic\s+(article|essay))\b", re.I),
    re.compile(r"\b(with\s+(sources|citations|references)|based\s+on\s+(sources|research|data))\b", re.I),
    re.compile(r"\b(about|on|regarding|concerning|explaining|analyzing)\s+\w{4,}\b", re.I),
    # Greek
    re.compile(r"\b(έρευνα|μελέτη|ενημερωτικό|με\s+πηγές|με\s+αναφορές)\b", re.I),
    re.compile(r"\b(για\s+(την|τον|τη|το|τους|τις|τα)\s+\w{4,}|σχετικά\s+με\s+\w{4,})\b", re.I),
]

# Hard research indicators — if these appear with creative verbs, treat as research-backed
# (requires full pipeline with search, NOT creative fast-path).
_HARD_RESEARCH_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"\b(research\s+(article|paper|essay)|informative\s+(article|essay)|academic\s+(article|essay))\b", re.I),
    re.compile(r"\b(with\s+(sources|citations|references)|based\s+on\s+(sources|research|data))\b", re.I),
    # Greek
    re.compile(r"\b(έρευνα|μελέτη|ενημερωτικό|με\s+πηγές|με\s+αναφορές)\b", re.I),
]


_WRITING_INTENT = re.compile(
    r"\b(write|draft|compose|create|prepare|produce)\s+(an?\s+)?(article|essay|blog\s+post|report|explainer|whitepaper|paper)\b",
    re.I,
)


def _is_creative_writing(problem: str) -> bool:
    """Return True only for PURE creative tasks (no research needed).

    Research-backed requests like "write an article about climate change"
    return False because they don't match _CREATIVE_PATTERNS.
    Pure creative requests like "write a poem about cats" return True
    even with a topic, unless they explicitly ask for sources/research.
    """
    # Must match a creative pattern first
    if not any(p.search(problem) for p in _CREATIVE_PATTERNS):
        return False
    # If hard research indicators are present (sources, academic, etc.), it's NOT pure creative
    if any(p.search(problem) for p in _HARD_RESEARCH_INDICATORS):
        return False
    return True

logger = logging.getLogger(__name__)

# ── Sentinel output used when asyncio.gather returns an exception ─────


def _failed_output(agent_name: str, exc: BaseException) -> SubAgentOutput:
    return SubAgentOutput(
        agent_name=agent_name,
        result={},
        confidence=0.0,
        reasoning="",
        tokens_in=0,
        tokens_out=0,
        model="unknown",
        duration_ms=0.0,
        error=str(exc),
    )


class HyperGateAgent:
    """
    Hyperagent that spawns 5 specialised sub-agents (one job each) in parallel,
    then synthesises their outputs into a final GateDecision.
    """

    _MAX_CACHE: int = HYPERGATE_CACHE_SIZE

    def __init__(self, router: ProviderRouter) -> None:
        self.router = router
        self._cache: dict[str, GateDecision] = {}
        self._lang = LanguageDetectorSubAgent()
        self._complexity = ComplexityEstimatorSubAgent()
        self._direct = DirectDetectorSubAgent()
        self._web = WebSearchDetectorSubAgent()
        self._method = MethodClassifierSubAgent()
        self._tiebreaker = TieBreakerSubAgent()

    # ── Public API (same signature as GateAgent.decide) ──────────────

    async def decide(self, problem: str) -> GateDecision:
        """Return a routing decision. Never raises — falls back to pipeline on any error."""
        problem_hash = hashlib.sha256(problem.encode()).hexdigest()
        if cached := self._cache.get(problem_hash):
            logger.debug("HyperGateAgent top-level cache hit hash=%s…", problem_hash[:16])
            return cached

        if len(problem.strip()) < 10:
            return GateDecision(
                action="direct", confidence=1.0, reasoning="Very short prompt, assumed direct",
                complexity="simple"
            )

        # Fast-path: simple factual lookups (e.g., "What is X?")
        # If it's a short, simple factual question, bypass the pipeline
        if any(p.search(problem) for p in _FACTUAL_PATTERNS) and len(problem) < 60:
            decision = GateDecision(
                action="direct",
                method=None,
                confidence=0.95,
                reasoning="Detected simple factual lookup, assumed direct answer",
                complexity="simple"
            )
            self._cache[problem_hash] = decision
            logger.info(
                "HyperGateAgent fast-path: factual-lookup hash=%s action=direct",
                problem_hash[:16],
            )
            return decision

        # Fast-path: research-backed writing (articles/essays/blog posts/reports)
        if _WRITING_INTENT.search(problem) or any(p.search(problem) for p in _RESEARCH_INDICATORS):
            decision = GateDecision(
                action="pipeline",
                method="writing",
                confidence=0.92,
                reasoning="Detected research-backed writing intent (article/essay/blog/report)",
                complexity="complex"
            )
            self._cache[problem_hash] = decision
            logger.info(
                "HyperGateAgent fast-path: writing-intent hash=%s action=pipeline method=writing",
                problem_hash[:16],
            )
            return decision

        ctx = await self._run_phase1(problem)
        decision = self._synthesize(ctx)

        if decision is None:
            decision = await self._run_tiebreaker(ctx)

        logger.info(
            "HyperGateAgent hash=%s action=%s method=%s confidence=%.2f",
            problem_hash[:16],
            decision.action,
            decision.method,
            decision.confidence,
        )

        if decision.confidence >= HYPERGATE_METHOD_THRESHOLD and (
            not decision.reasoning or "fallback" not in decision.reasoning.lower()
        ):
            self._cache[problem_hash] = decision
            if len(self._cache) > self._MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))

        return decision

    # ── Phase 1: all 5 sub-agents in parallel ────────────────────────

    async def _run_phase1(self, problem: str) -> HyperContext:
        inp = SubAgentInput(problem=problem, agent_name="phase1")
        results = await asyncio.gather(
            self._lang.execute(inp, self.router),
            self._complexity.execute(inp, self.router),
            self._direct.execute(inp, self.router),
            self._web.execute(inp, self.router),
            self._method.execute(inp, self.router),
            return_exceptions=True,
        )

        def _unwrap(res: SubAgentOutput | BaseException, name: str) -> SubAgentOutput:
            if isinstance(res, BaseException):
                logger.error("[phase1/%s] sub-agent failed: %s", name, res, exc_info=res)
                return _failed_output(name, res)
            return res

        lang_out, cpx_out, dir_out, web_out, mth_out = (
            _unwrap(results[0], "language_detector"),
            _unwrap(results[1], "complexity_estimator"),
            _unwrap(results[2], "direct_detector"),
            _unwrap(results[3], "web_detector"),
            _unwrap(results[4], "method_classifier"),
        )
        return HyperContext(
            problem=problem,
            lang_output=lang_out,
            complexity_output=cpx_out,
            direct_output=dir_out,
            web_output=web_out,
            method_output=mth_out,
        )

    # ── Synthesis (pure Python, no LLM) ─────────────────────────────

    def _synthesize(self, ctx: HyperContext) -> GateDecision | None:
        """
        Return a GateDecision when signals are clear; return None to trigger TieBreaker.
        """
        direct_conf = ctx.direct_output.confidence if not ctx.direct_output.error else 0.0
        web_conf = ctx.web_output.confidence if not ctx.web_output.error else 0.0
        method_conf = ctx.method_output.confidence if not ctx.method_output.error else 0.0
        complexity = ctx.complexity

        is_direct = ctx.direct_output.result.get("is_direct", False)
        needs_search = ctx.web_output.result.get("needs_search", False)
        category = ctx.method_output.result.get("category", "E")
        method_name = ctx.method_output.result.get("method", "multi_perspective")

        # Conflict: DirectDetector says direct but method classifier is very confident
        # about a non-trivial method AND the problem is not actually simple.
        direct_method_conflict = (
            is_direct
            and method_conf > 0.75
            and complexity != "simple"
        )

        # Overlap: web search need + research pipeline method — let TieBreaker decide.
        web_research_overlap = needs_search and category == "G"

        # Step 1 — direct answer
        if (
            is_direct
            and direct_conf >= HYPERGATE_DIRECT_THRESHOLD
            and complexity == "simple"
            and not direct_method_conflict
        ):
            return GateDecision(
                action="direct",
                method=None,
                confidence=direct_conf,
                reasoning=ctx.direct_output.reasoning or "DirectDetector: simple direct query",
                complexity=complexity
            )

        # Step 2 — web search
        if needs_search and web_conf >= HYPERGATE_WEB_THRESHOLD and not web_research_overlap:
            return GateDecision(
                action="web_search",
                method=None,
                confidence=web_conf,
                reasoning=ctx.web_output.reasoning or "WebDetector: real-time data required",
                complexity=complexity
            )

        # Step 3 — pipeline with clear method
        if method_conf >= HYPERGATE_METHOD_THRESHOLD:
            return GateDecision(
                action="pipeline",
                method=method_name,
                confidence=method_conf,
                reasoning=ctx.method_output.reasoning or f"MethodClassifier: {category}",
                complexity=complexity
            )

        # Step 4 — ambiguous but some signal: defer to TieBreaker
        if any(c >= HYPERGATE_AMBIGUOUS_FLOOR for c in (direct_conf, web_conf, method_conf)):
            return None

        # Step 5 — all failed / all below floor: hard fallback
        return GateDecision(
            action="pipeline",
            method="multi_perspective",
            confidence=0.0,
            reasoning="All sub-agents failed or returned very low confidence, fallback",
            complexity=complexity
        )

    # ── Phase 2: TieBreaker ──────────────────────────────────────────

    async def _run_tiebreaker(self, ctx: HyperContext) -> GateDecision:
        logger.info("HyperGateAgent triggering TieBreaker (ambiguous Phase-1 signals)")
        tb_input = SubAgentInput(
            problem=ctx.problem,
            agent_name="tie_breaker",
            context=ctx.to_dict(),
        )
        out = await self._tiebreaker.execute(tb_input, self.router)
        if out.error:
            return GateDecision(
                action="pipeline",
                method="multi_perspective",
                confidence=0.0,
                reasoning="TieBreaker failed, fallback to pipeline",
            )
        action: Literal["direct", "pipeline", "web_search"] = out.result.get("action", "pipeline")  # type: ignore[assignment]
        return GateDecision(
            action=action,
            method=out.result.get("method"),
            confidence=out.confidence,
            reasoning=out.reasoning or "TieBreaker resolution",
            complexity=ctx.complexity
        )
