"""Shared augmentation pre-processing for article and writing flows.

When a question is detected as deep/abstract, runs debate + iterative critique
in parallel before the main pipeline phases, storing enriched context in
state.writing_state["pre_research_insights"].

The result cache below is L1 (in-process) only: per-worker, not shared across
uvicorn workers or restarts. That's an accepted limitation of an in-memory
cache, not an oversight.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import Any

from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

# ── Augmentation result cache (L1: in-memory LRU) ─────────────────────

_aug_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _make_cache_key(problem: str) -> str:
    """Derive a stable cache key from the problem text."""
    return hashlib.sha256(problem.strip().lower().encode()).hexdigest()


def _get_cached(problem: str) -> dict[str, Any] | None:
    """Check L1 cache for a prior augmentation result.

    Returns None on miss, or the cached insights dict on hit.
    """
    key = _make_cache_key(problem)
    if key in _aug_cache:
        entry = _aug_cache.pop(key)
        _aug_cache[key] = entry  # Move to end (LRU bump)
        # Check TTL
        from reasoner.core.settings import settings
        age = time.time() - entry["_ts"]
        if age < settings.AUGMENTATION_CACHE_TTL_SECONDS:
            logger.debug("Augmentation L1 cache hit for %s… (age=%.0fs)", key[:16], age)
            return entry
        # Expired — remove
        del _aug_cache[key]
        logger.debug("Augmentation L1 cache expired for %s…", key[:16])
    return None


def _set_cache(problem: str, insights: dict[str, str], summary: str) -> None:
    """Store augmentation results in L1 (and optionally L2) cache.

    Busted on follow-up turns by the caller (turn_number > 1 skips cache entirely).
    """
    from reasoner.core.settings import settings
    if not settings.AUGMENTATION_CACHE_ENABLED:
        return
    key = _make_cache_key(problem)
    entry = {"insights": insights, "summary": summary, "_ts": time.time()}
    _aug_cache[key] = entry
    # Evict oldest if over capacity
    while len(_aug_cache) > settings.AUGMENTATION_CACHE_MAX_ENTRIES:
        _aug_cache.popitem(last=False)
    logger.debug("Augmentation L1 cache stored for %s… (%d entries)", key[:16], len(_aug_cache))

# ── Depth detection: regex-based heuristic for deep/abstract questions ──
# Matches questions that are philosophical, abstract, definitional, or ethically
# complex. These benefit from pre-processing (debate, critique, multi-perspective)
# before drafting.

_DEEP_QUESTION_PATTERNS: list[re.Pattern[str]] = [
    # Greek patterns
    re.compile(r"\b(τι\s+(\S+\s+)?είναι|ποια\s+είναι\s+η\s+έννοια|ορίστε|ορισμός\s+του|φύση\s+(του|της)|υπόσταση\s+του)\b", re.I),
    re.compile(r"\b(φιλοσοφία|ηθική|αισθητική|οντολογία|επιστημολογία|μεταφυσική|υπαρξισμός)\b", re.I),
    re.compile(r"\b(νοήματος\s+της\s+ζωής|συνείδηση|ελεύθερη\s+βούληση|δικαιοσύνη|αλήθεια|ομορφιά)\b", re.I),
    # English patterns
    re.compile(r"\b(what\s+is\s+(the\s+)?(meaning|nature|essence|definition|purpose|concept)\s+of)\b", re.I),
    re.compile(r"\b(what\s+(exactly\s+)?is\s+(art|love|beauty|truth|justice|consciousness|reality|knowledge|time|god|freedom|morality|happiness|wisdom|existence))\b", re.I),
    re.compile(r"\b(philosophy|ethics|aesthetics|ontology|epistemology|metaphysics|existentialism)\b", re.I),
    re.compile(r"\b(meaning\s+of\s+life|consciousness|free\s+will|justice|truth|beauty)\b", re.I),
    re.compile(r"\b(is\s+there\s+(a|such\s+thing\s+as)|can\s+we\s+(ever|truly|really))\b", re.I),
    # Cross-language abstract markers
    re.compile(r"\b(ορίζεται|ορισμός|έννοια|υπόσταση|συνείδηση|ύπαρξη)\b", re.I),
]

# Default augmentation methods for deep questions
DEFAULT_AUGMENTATION_METHODS = ["debate", "iterative_critique"]

# ── Augmentation prompts ──────────────────────────────────────────────

_AUGMENTATION_DEBATE_SYSTEM = (
    "You are a debate analyst. Given a question, produce a structured pro/con analysis "
    "with 3-4 arguments on each side, then a brief synthesis that identifies the key "
    "tensions and insights. Output in Greek if the question is in Greek, otherwise English. "
    "Keep it under 800 words. Focus on depth, not breadth."
)

_AUGMENTATION_CRITIQUE_SYSTEM = (
    "You are an adversarial critic. Given a question, generate a preliminary answer, "
    "then critique it mercilessly — identify hidden assumptions, logical gaps, missing "
    "perspectives, and weak evidence. Then produce a refined version. "
    "Output in Greek if the question is in Greek, otherwise English. "
    "Keep it under 800 words. Be intellectually honest: the goal is better understanding."
)

_AUGMENTATION_MULTI_PERSPECTIVE_SYSTEM = (
    "You are a multi-perspective analyst. Given a question, produce 3-4 distinct "
    "viewpoints from different traditions or frameworks (e.g., philosophical, scientific, "
    "cultural, historical). Each viewpoint should be internally coherent, even if they "
    "contradict each other. Then identify what each perspective reveals that the others miss. "
    "Output in Greek if the question is in Greek, otherwise English. "
    "Keep it under 800 words."
)

_AUGMENTATION_JURY_SYSTEM = (
    "You are a jury of experts from different disciplines evaluating a question. "
    "Produce a weighted panel analysis: 3-4 expert voices (e.g., philosopher, scientist, "
    "artist, historian) each giving their best answer, with confidence scores and reasoning. "
    "Then provide a weighted synthesis. "
    "Output in Greek if the question is in Greek, otherwise English. "
    "Keep it under 800 words."
)

_AUGMENTATION_SOCRATIC_SYSTEM = (
    "You are a Socratic examiner. Given a question, produce a chain of 5-7 "
    "progressively deeper follow-up questions that expose the hidden assumptions, "
    "unexamined premises, and definitional ambiguities in the original question. "
    "Each question should force a re-examination of what was taken for granted. "
    "Do NOT answer any of the questions — your job is only to excavate assumptions "
    "by asking the right questions. End with a brief (2-3 sentence) summary of the "
    "key assumptions you uncovered. "
    "Output in Greek if the question is in Greek, otherwise English. "
    "Keep it under 800 words."
)

AUGMENTATION_PROMPTS: dict[str, str] = {
    "debate": _AUGMENTATION_DEBATE_SYSTEM,
    "iterative_critique": _AUGMENTATION_CRITIQUE_SYSTEM,
    "multi_perspective": _AUGMENTATION_MULTI_PERSPECTIVE_SYSTEM,
    "jury": _AUGMENTATION_JURY_SYSTEM,
    "socratic": _AUGMENTATION_SOCRATIC_SYSTEM,
}

AUGMENTATION_ROLES: dict[str, str] = {
    "debate": "primary",
    "iterative_critique": "primary",
    "multi_perspective": "primary",
    "jury": "primary",
    "socratic": "primary",
}


def is_deep_question(problem: str) -> bool:
    """Check if a problem is a deep/abstract question using regex heuristics."""
    return any(p.search(problem) for p in _DEEP_QUESTION_PATTERNS)


_DEPTH_CONFIRM_SYSTEM = (
    "You are a routing classifier. Your only job is to answer YES or NO: "
    "Is the user's question fundamentally philosophical, abstract, or definitional "
    "(requiring multi-perspective reasoning) rather than a simple factual or "
    "practical question? Answer with exactly one word: YES or NO."
)


async def confirm_depth(problem: str, call_llm, log, state: PipelineState) -> bool:
    """LLM-based depth confirmation — filters regex false positives.

    Only called when AUGMENTATION_LLM_CONFIRM=true and the regex heuristic
    flagged the question as deep. Makes one small LLM call to confirm.
    Returns True if the LLM confirms the question is deep.
    """
    try:
        raw, _meta = await call_llm(
            role="primary",
            system_prompt=_DEPTH_CONFIRM_SYSTEM,
            user_prompt=problem,
            state=state,
            phase_key="augment_depth_confirm",
            max_tokens=8,
            temperature=0.0,
        )
        result = raw.strip().upper()
        is_confirmed = result.startswith("YES")
        log("AUGMENT", f"LLM depth confirmation: {'YES' if is_confirmed else 'NO'} (raw: {result[:50]})", state)
        return is_confirmed
    except Exception as exc:
        # Deliberate fail-open: this is a quality filter refining the regex
        # heuristic, not a safety gate — on failure, trust the regex verdict
        # rather than silently dropping augmentation for an unrelated error.
        logger.warning("LLM depth confirmation failed: %s. Falling back to regex result.", exc)
        return True


async def run_augmentation(
    state: PipelineState,
    call_llm,
    log,
) -> None:
    """Run pre-processing augmentation methods before the main pipeline phases.

    Uses regex-based heuristic to detect deep/abstract questions, then runs
    debate + iterative critique in parallel. Stores combined insights in
    state.writing_state["pre_research_insights"].

    Args:
        state: Current pipeline state.
        call_llm: Async callable with signature (role, system_prompt, user_prompt,
                  state, phase_key, **kwargs) -> tuple[str, dict].
        log: Callable with signature (phase, message, state) -> None.
    """
    if not is_deep_question(state.problem):
        return

    from reasoner.core.settings import settings
    if not settings.AUGMENTATION_ENABLED:
        log("AUGMENT", "Augmentation disabled via AUGMENTATION_ENABLED=false", state)
        return

    # ── Resolve methods before anything billable ──
    # None = no preference (tests, direct construction) → default pair.
    # []   = explicit "no augmentation" (budget tier) → must not fall back,
    #        that's the entire point of the tier — skip before spending a cent.
    configured = state.meta.augmentation_methods
    methods = DEFAULT_AUGMENTATION_METHODS if configured is None else configured
    if not methods:
        log("AUGMENT", "No augmentation methods configured for this tier — skipping", state)
        return

    # ── Cache check: skip LLM calls on repeated deep questions ──
    # Only cache first-turn questions; follow-up turns have different context.
    # Checked before the (billable) LLM depth confirmation below — a cached
    # entry was already depth-confirmed when it was stored.
    is_first_turn = getattr(state, "turn_number", 1) <= 1
    if is_first_turn and settings.AUGMENTATION_CACHE_ENABLED:
        if cached := _get_cached(state.problem):
            state.writing_state["pre_research_insights"] = cached["insights"]
            state.writing_state["pre_research_summary"] = cached["summary"]
            log("AUGMENT", "Cache hit — reused prior augmentation results", state)
            return

    # ── Optional LLM depth confirmation (premium-tier quality filter) ──
    if settings.AUGMENTATION_LLM_CONFIRM:
        if not await confirm_depth(state.problem, call_llm, log, state):
            log("AUGMENT", "LLM depth confirmation rejected — skipping augmentation", state)
            return

    log("AUGMENT", f"Running pre-processing: {', '.join(methods)}", state)

    async def _run_one(method: str) -> tuple[str, str]:
        system = AUGMENTATION_PROMPTS.get(method, _AUGMENTATION_DEBATE_SYSTEM)
        role = AUGMENTATION_ROLES.get(method, "primary")
        try:
            raw, _meta = await call_llm(
                role=role,
                system_prompt=system,
                user_prompt=state.problem,
                state=state,
                phase_key=f"augment_{method}",
                max_tokens=2048,
                temperature=0.7,
            )
            return method, raw
        except Exception as exc:
            logger.warning("Augmentation method '%s' failed: %s", method, exc)
            return method, f"[Failed: {exc}]"

    # Run augmentation methods in parallel
    tasks = [_run_one(m) for m in methods]
    results = await asyncio.gather(*tasks)

    # Store results
    insights: dict[str, str] = {}
    for method, content in results:
        insights[method] = content

    state.writing_state["pre_research_insights"] = insights

    # Build a combined summary for injection into pipeline phases
    summary_parts = []
    for method, content in insights.items():
        if content and not content.startswith("[Failed"):
            truncated = content[:600] + ("..." if len(content) > 600 else "")
            summary_parts.append(f"### {method.upper()} FINDINGS\n{truncated}")
    state.writing_state["pre_research_summary"] = "\n\n".join(summary_parts)

    # ── Cache the results for future identical questions ──
    if is_first_turn:
        _set_cache(state.problem, insights, state.writing_state["pre_research_summary"])

    log(
        "AUGMENT",
        f"Pre-processing complete: {len(insights)} methods, "
        f"{sum(len(v) for v in insights.values())} total chars",
        state,
    )


def get_tier_augmentation_methods(tier: str) -> list[str]:
    """Return augmentation methods appropriate for a pricing tier.

    Budget  → no augmentation (cost-sensitive)
    Premium → debate + iterative critique + jury + socratic
    Default → debate only (single extra call)
    """
    if tier == "budget":
        return []
    if tier == "premium":
        return ["debate", "iterative_critique", "jury", "socratic"]
    return ["debate"]
