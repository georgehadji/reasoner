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
from reasoner.hypergate.gate_agent import GateDecision
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

# Fast-path patterns for clearly real-time queries that require a live web search.
# Checked before factual and writing patterns so temporal queries are never mislabeled.
_REALTIME_PATTERNS: list[re.Pattern[str]] = [
    # Price / market data with explicit temporal marker
    re.compile(r"\bprice\b.{0,30}\b(now|today|right now|currently|live)\b", re.I),
    re.compile(r"\b(now|today|right now|currently|live)\b.{0,30}\bprice\b", re.I),
    re.compile(r"\b(current|live|real.?time)\s+(price|rate|exchange rate|value|cost)\b", re.I),
    # News and recent events
    re.compile(r"\b(latest|breaking|today'?s?|current)\s+(news|headline|update|development)\b", re.I),
    re.compile(r"\bnews\b.{0,20}\b(today|right now|latest|breaking)\b", re.I),
    re.compile(r"\blatest\b.{0,50}\b(release|launch|update|announcement|version)\b", re.I),
    # Weather
    re.compile(r"\b(weather|temperature|forecast)\b.{0,25}\b(today|now|right now|this week|tomorrow)\b", re.I),
    re.compile(r"\b(today'?s?|current|live)\s+weather\b", re.I),
    # Sports live scores
    re.compile(r"\b(live|current)\s+(score|match|game|result|standings?)\b", re.I),
    re.compile(r"\b(score|result)\b.{0,20}\b(live|now|today)\b", re.I),
    # Greek
    re.compile(r"\b(τελευταία|πρόσφατη?|σημερινή)\s+(είδηση|νέα|τιμή|ανακοίνωση)\b", re.I),
    re.compile(r"\b(τρέχουσα|ζωντανή)\s+(τιμή|αποτέλεσμα)\b", re.I),
]

# Fast-path patterns for simple factual lookups that can be answered directly
# by a knowledge model (no web search or multi-phase reasoning needed).
_FACTUAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(what\s+is|who\s+is|where\s+is|when\s+is|how\s+many|define|explain)\s+(the\s+)?\w+", re.I),
    re.compile(r"\b(capital\s+of|president\s+of|invented)\s+\w+", re.I),
    re.compile(r"\b(τι\s+είναι|ποιο\s+είναι|ποιος\s+είναι|πού\s+είναι|πότε\s+είναι|πόσα|πόσες|πόσους|ορίζω|εξήγησε)\s+(το\s+|η\s+|ο\s+)?\w+", re.I),
    re.compile(r"\b(πρωτεύουσα\s+της|πρόεδρος\s+της|εφεύρε)\s+\w+", re.I),
]

# Abstract concept patterns that should NEVER be treated as simple factual lookups.
# When these concepts appear, the query needs multi-phase reasoning even if it looks
# like a simple "what is X?" question.
_DEEP_CONCEPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(art|beauty|truth|justice|consciousness|reality|knowledge|time|god|freedom|morality|happiness|wisdom|existence|love|ethics|meaning|purpose|soul|infinity|nothingness|being|becoming)\b", re.I),
    re.compile(r"\b(τέχνη|τέχνες|ομορφιά|αλήθεια|δικαιοσύνη|συνείδηση|πραγματικότητα|γνώση|ελευθερία|ηθική|ύπαρξη|αισθητική|οντολογία|νοήματος|θεός|ψυχή|άπειρο)\b", re.I),
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

    async def _get_l2_cache(self, problem_hash: str) -> GateDecision | None:
        """L2 cache lookup disabled (moved to orchestrator layer to avoid arch violation)."""
        return None

    async def _set_l2_cache(self, problem_hash: str, decision: GateDecision) -> None:
        """L2 cache save disabled (moved to orchestrator layer to avoid arch violation)."""
        pass

    @staticmethod
    def _safe_create_task(coro, name: str) -> None:
        """Spawn a fire-and-forget task with exception logging."""
        import asyncio
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(
            lambda t: logger.warning(
                "Background task '%s' failed: %s", name, t.exception()
            ) if t.exception() and not t.cancelled() else None
        )

    def _cache_set(self, problem_hash: str, decision: GateDecision) -> None:
        """Set in L1 and dispatch async task for L2."""
        self._cache[problem_hash] = decision
        if len(self._cache) > self._MAX_CACHE:
            self._cache.pop(next(iter(self._cache)))
        # Fire-and-forget L2 set to not block the critical path
        self._safe_create_task(
            self._set_l2_cache(problem_hash, decision),
            "hypergate_l2_cache_set",
        )

    # ── Public API (same signature as GateAgent.decide) ──────────────

    async def decide(self, problem: str) -> GateDecision:
        """Return a routing decision. Never raises — falls back to pipeline on any error."""
        problem_hash = hashlib.sha256(problem.encode()).hexdigest()
        if cached := self._cache.get(problem_hash):
            logger.debug("HyperGateAgent top-level cache hit hash=%s…", problem_hash[:16])
            return cached

        # Try L2 cache
        if l2_cached := await self._get_l2_cache(problem_hash):
            logger.debug("HyperGateAgent L2 cache hit hash=%s…", problem_hash[:16])
            # Warm up L1
            self._cache[problem_hash] = l2_cached
            if len(self._cache) > self._MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))
            return l2_cached

        if len(problem.strip()) < 10:
            return GateDecision(
                action="direct", confidence=1.0, reasoning="Very short prompt, assumed direct",
                complexity="simple"
            )

        # Fast-path: research-backed writing (articles/essays/blog posts/reports)
        # Checked first so "write an article about latest news" routes to writing, not web_search.
        if _WRITING_INTENT.search(problem):
            decision = GateDecision(
                action="pipeline",
                method="writing",
                confidence=0.92,
                reasoning="Detected research-backed writing intent (article/essay/blog/report)",
                complexity="complex"
            )
            self._cache_set(problem_hash, decision)
            logger.info(
                "HyperGateAgent fast-path: writing-intent hash=%s action=pipeline method=writing",
                problem_hash[:16],
            )
            return decision

        # Fast-path: obvious real-time data queries (prices, live news, weather, scores)
        if any(p.search(problem) for p in _REALTIME_PATTERNS):
            decision = GateDecision(
                action="web_search",
                method=None,
                confidence=0.92,
                reasoning="Detected real-time data query (prices/news/weather/scores)",
                complexity="simple",
            )
            self._cache_set(problem_hash, decision)
            logger.info(
                "HyperGateAgent fast-path: realtime hash=%s action=web_search",
                problem_hash[:16],
            )
            return decision

        # Fast-path: simple factual lookups (e.g., "What is X?")
        # Skip if the question contains deep/abstract concepts that need multi-phase reasoning.
        is_deep_concept = any(p.search(problem) for p in _DEEP_CONCEPT_PATTERNS)
        if any(p.search(problem) for p in _FACTUAL_PATTERNS) and len(problem) < 60 and not is_deep_concept:
            decision = GateDecision(
                action="direct",
                method=None,
                confidence=0.95,
                reasoning="Detected simple factual lookup, assumed direct answer",
                complexity="simple",
            )
            self._cache_set(problem_hash, decision)
            logger.info(
                "HyperGateAgent fast-path: factual-lookup hash=%s action=direct",
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
            self._cache_set(problem_hash, decision)

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
        candidates = ctx.method_output.result.get("candidates", []) or []
        # Alternatives = candidates other than the top pick, already sorted by confidence.
        method_alternatives = [
            {"method": c["method"], "confidence": c["confidence"], "rationale": c["rationale"]}
            for c in candidates
            if c.get("method") != method_name
        ] or None

        # ── Depth detection moved to ArticleFlow (regex-based, no LLM overhead) ──
        augmentation_methods: list[str] | None = None

        # Conflict: DirectDetector says direct but method classifier is very confident
        # about a non-trivial method AND the problem is not actually simple.
        direct_method_conflict = (
            is_direct
            and method_conf > 0.75
            and complexity != "simple"
        )

        # Overlap: web search need + research pipeline method — defer to TieBreaker,
        # but only when WebDetector is not clearly confident. A high web_conf (≥ 0.85)
        # means the query is plainly real-time and wins over the research method label.
        web_research_overlap = needs_search and category == "G" and web_conf < 0.85

        # Research-heavy queries: force pipeline even when DirectDetector says direct.
        # Prevents misrouting of queries like 'room-temperature superconductivity
        # breakthroughs' that Claude classifies as simple known-fact questions.
        research_override = any(
            p.search(ctx.problem)
            for p in _RESEARCH_INDICATORS
        ) if ctx.problem else False

        # Step 1 — direct answer
        if (
            is_direct
            and direct_conf >= HYPERGATE_DIRECT_THRESHOLD
            and complexity == "simple"
            and not direct_method_conflict
            and not research_override
        ):
            return GateDecision(
                action="direct",
                method=None,
                confidence=direct_conf,
                reasoning=ctx.direct_output.reasoning or "DirectDetector: simple direct query",
                complexity=complexity,
                augmentation_methods=None,
            )

        # Step 2 — web search
        if needs_search and web_conf >= HYPERGATE_WEB_THRESHOLD and not web_research_overlap:
            return GateDecision(
                action="web_search",
                method=None,
                confidence=web_conf,
                reasoning=ctx.web_output.reasoning or "WebDetector: real-time data required",
                complexity=complexity,
                augmentation_methods=None,
            )

        # Step 3 — pipeline with clear method
        if method_conf >= HYPERGATE_METHOD_THRESHOLD:
            return GateDecision(
                action="pipeline",
                method=method_name,
                confidence=method_conf,
                reasoning=ctx.method_output.reasoning or f"MethodClassifier: {category}",
                complexity=complexity,
                augmentation_methods=augmentation_methods,
                alternatives=method_alternatives,
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
            complexity=complexity,
            augmentation_methods=None,
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
                augmentation_methods=None,
            )
        action: Literal["direct", "pipeline", "web_search"] = out.result.get("action", "pipeline")  # type: ignore[assignment]
        chosen_method = out.result.get("method")
        candidates = ctx.method_output.result.get("candidates", []) or []
        tiebreak_alternatives = [
            {"method": c["method"], "confidence": c["confidence"], "rationale": c["rationale"]}
            for c in candidates
            if c.get("method") != chosen_method
        ] or None
        return GateDecision(
            action=action,
            method=chosen_method,
            confidence=out.confidence,
            reasoning=out.reasoning or "TieBreaker resolution",
            complexity=ctx.complexity,
            augmentation_methods=None,
            alternatives=tiebreak_alternatives if action == "pipeline" else None,
        )
