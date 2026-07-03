"""Rule-based phase quality criteria and state reset functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from reasoner.domain.pipeline_state import PipelineState


@dataclass
class PhaseQualityResult:
    passed: bool
    score: float  # 0.0 – 10.0
    reason: str
    suggestions: list[str] = field(default_factory=list)


def _ok(score: float = 9.0) -> PhaseQualityResult:
    return PhaseQualityResult(passed=True, score=score, reason="Quality checks passed.")


def _fail(reason: str, suggestions: list[str] | None = None, score: float = 2.0) -> PhaseQualityResult:
    return PhaseQualityResult(passed=False, score=score, reason=reason, suggestions=suggestions or [])


# ─────────────────────────────────────────────────────────────────────────────
# Per-phase rule functions
# ─────────────────────────────────────────────────────────────────────────────

def _check_classification(state: PipelineState) -> PhaseQualityResult:
    if state.task_type is None:
        return _fail(
            "task_type was not set by Classification.",
            ["Ensure the LLM returns a valid task_type JSON field."],
        )
    return _ok()


def _check_decomposition(state: PipelineState) -> PhaseQualityResult:
    d = state.decomposition
    if not d:
        return _fail(
            "Decomposition produced no sub-problems.",
            ["Return at least one sub-problem in the decomposition JSON."],
        )
    if isinstance(d, dict):
        items = d.get("sub_problems", []) or list(d.values()) or [d]
    elif isinstance(d, list):
        items = d
    else:
        items = getattr(d, "sub_problems", None) or []
    if len(items) == 0:
        return _fail(
            "Decomposition list is empty.",
            ["Include 1–5 meaningful sub-problems in the response."],
        )
    return _ok()


def _check_perspectives(state: PipelineState) -> PhaseQualityResult:
    if not state.candidates:
        return _fail(
            "No perspective candidates were generated.",
            ["Ensure at least one perspective LLM call succeeds and returns non-empty content."],
        )
    thin = [c for c in state.candidates if len(getattr(c, "content", "") or "") < 50]
    if len(thin) == len(state.candidates):
        return _fail(
            f"All {len(state.candidates)} perspective(s) have very short content (<50 chars).",
            ["Increase max_tokens budget or check for truncation / parse errors."],
            score=3.0,
        )
    if len(thin) > 0:
        return PhaseQualityResult(
            passed=True,
            score=6.5,
            reason=f"{len(thin)}/{len(state.candidates)} perspective(s) are thin but usable.",
        )
    return _ok(score=9.0)


def _check_critique(state: PipelineState) -> PhaseQualityResult:
    if not state.scores:
        return _fail(
            "Critique produced no scores.",
            ["Ensure the scoring LLM returns a valid 'scores' JSON array."],
        )
    if not state.top_candidates:
        return _fail(
            "Pruning produced no top_candidates.",
            ["Check that top_k <= number of candidates and scoring didn't error."],
        )
    bad_scores = []
    for s in state.scores:
        total = getattr(s, "total", None)
        if total is not None and not (0.0 <= total <= 10.0):
            bad_scores.append(str(total))
    if bad_scores:
        return _fail(
            f"Scores out of range [0-10]: {', '.join(bad_scores[:3])}.",
            ["Instruct the model to return scores strictly between 0 and 10."],
            score=4.0,
        )
    return _ok()


def _check_stress_testing(state: PipelineState) -> PhaseQualityResult:
    if not state.stress_results:
        return _fail(
            "Stress testing produced no results.",
            ["Ensure the LLM returns a 'stress_tests' JSON array with at least one entry."],
        )
    bad = [
        r for r in state.stress_results
        if not (0.0 <= getattr(r, "survival_rate", 0.5) <= 1.0)
    ]
    if bad:
        return _fail(
            f"{len(bad)} stress result(s) have survival_rate outside [0,1].",
            ["Return survival_rate as a float between 0.0 and 1.0."],
            score=4.0,
        )
    return _ok()


def _check_synthesis(state: PipelineState) -> PhaseQualityResult:
    sol = state.final_solution
    if sol is None:
        return _fail(
            "Synthesis produced no final_solution.",
            ["Ensure the synthesis LLM returns a valid final_solution JSON object."],
        )
    core = getattr(sol, "core_solution", "") or ""
    if len(core) < 100:
        return _fail(
            f"core_solution is too short ({len(core)} chars, minimum 100).",
            ["Request a more detailed core_solution in the synthesis prompt."],
            score=3.0,
        )
    insights = getattr(sol, "critical_insights", []) or []
    if len(insights) == 0:
        return PhaseQualityResult(
            passed=True,
            score=6.0,
            reason="Synthesis complete but critical_insights is empty.",
        )
    return _ok()


# ── Writing phase checks ──────────────────────────────────────────────────────

def _check_decompose_topic(state: PipelineState) -> PhaseQualityResult:
    ws = state.writing_state
    if not ws.get("subquestions"):
        return _fail(
            "Decompose Topic produced no subquestions.",
            ["Return a non-empty 'subquestions' list in the JSON response."],
        )
    return _ok()


def _check_retrieve_sources(state: PipelineState) -> PhaseQualityResult:
    sources = state.writing_state.get("retrieved_sources", [])
    if not sources:
        return _fail(
            "Retrieve Sources found no sources.",
            ["Check search backend availability; fall back to knowledge-only synthesis."],
            score=4.0,
        )
    return _ok()


def _check_extract_claims(state: PipelineState) -> PhaseQualityResult:
    reviews = state.writing_state.get("factcheck_reviews", [])
    if not reviews:
        return _fail(
            "Extract Claims (CoVE) produced no factcheck_reviews.",
            ["Ensure the LLM extracts verifiable claims from the retrieved sources."],
        )
    return _ok()


def _check_final_assembly(state: PipelineState) -> PhaseQualityResult:
    article = state.writing_state.get("final_article", "") or ""
    if len(article) < 500:
        return _fail(
            f"Final Assembly article is too short ({len(article)} chars, minimum 500).",
            ["Request a longer, more detailed article in the assembly prompt."],
            score=3.0,
        )
    return _ok()


def _check_humanize(state: PipelineState) -> PhaseQualityResult:
    humanized = state.writing_state.get("humanized_article", "") or ""
    article = state.writing_state.get("final_article", "") or ""
    if not humanized and not article:
        return _fail(
            "Humanize produced no output.",
            ["Ensure the humanizer LLM returns non-empty content."],
        )
    return _ok()


def _check_context_vetting(state: PipelineState) -> PhaseQualityResult:
    vetted = getattr(state, "vetted_context", None) or []
    quality = getattr(state, "context_quality", "unknown")
    if not vetted:
        return _fail(
            "Context Vetting produced no vetted results.",
            ["Check that web search returned results and that the vetting step ran."],
            score=3.0,
        )
    if quality == "contaminated":
        return _fail(
            "Context quality flagged as contaminated — all results were unreliable.",
            ["Try a more specific search query or allow knowledge-only fallback."],
            score=4.0,
        )
    if quality == "missing":
        return _fail(
            "Context quality flagged as missing — no usable search context.",
            ["Ensure search backend is configured and reachable, or enable knowledge-only fallback."],
            score=4.0,
        )
    score = 7.0 if quality == "partial" else 9.0
    return PhaseQualityResult(
        passed=True,
        score=score,
        reason=f"Context vetting complete ({len(vetted)} results, quality={quality}).",
    )


def _check_deep_read(state: PipelineState) -> PhaseQualityResult:
    vetted = getattr(state, "vetted_context", None) or []
    if not vetted:
        return _fail(
            "Deep Read produced no vetted context entries.",
            ["Ensure sources are scraped or the knowledge-only fallback completed."],
            score=3.0,
        )
    # Require at least one entry with a non-trivial summary
    with_summaries = [
        v for v in vetted
        if isinstance(v, dict) and len(v.get("summary", "") or "") > 20
    ]
    if not with_summaries:
        return _fail(
            "Deep Read entries lack meaningful summaries.",
            ["Check that LLM extraction step completed and returned non-empty summaries."],
            score=4.0,
        )
    return _ok(score=9.0)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table
# ── Brainstorming / Verbalized Sampling checks ───────────────────────────────

def _check_brainstorm_generate(state: PipelineState) -> PhaseQualityResult:
    bs = getattr(state, "brainstorming_state", {}) or {}
    raw = bs.get("raw_ideas", [])
    if not raw:
        return _fail(
            "VS generation produced no ideas.",
            ["Check brainstorm_generate model routing and prompt."],
        )
    tail_ideas = [i for i in raw if i.get("probability", 1.0) < 0.15]
    if not tail_ideas:
        return PhaseQualityResult(
            passed=True,
            score=6.0,
            reason=(
                f"Generated {len(raw)} ideas but none have probability < 0.15 — "
                "diversity may be low (mode collapse not fully escaped)."
            ),
        )
    return _ok(score=9.0)


def _check_brainstorm_cluster(state: PipelineState) -> PhaseQualityResult:
    bs = getattr(state, "brainstorming_state", {}) or {}
    clusters = bs.get("clusters", [])
    top = bs.get("top_ideas", [])
    if not clusters:
        return _fail(
            "Clustering produced no clusters.",
            ["Ensure brainstorm_cluster model returns a 'clusters' array."],
        )
    if not top:
        return _fail(
            "No ideas were kept after clustering (all have keep=false).",
            ["Check the clustering prompt — ensure at least one idea per cluster has keep=true."],
            score=3.0,
        )
    return _ok()


def _check_brainstorm_develop(state: PipelineState) -> PhaseQualityResult:
    bs = getattr(state, "brainstorming_state", {}) or {}
    devs = bs.get("developments", [])
    if not devs:
        return _fail(
            "Deep development produced no developments.",
            ["Check brainstorm_develop model routing and prompt."],
        )
    thin = [d for d in devs if len(d.get("use_case", "") or "") < 50]
    if len(thin) == len(devs):
        return _fail(
            f"All {len(devs)} developments have thin use_case (<50 chars) — likely truncated.",
            ["Increase token budget for brainstorm_develop role."],
            score=4.0,
        )
    return _ok()


# ─────────────────────────────────────────────────────────────────────────────

_RULES: dict[str, Callable[[PipelineState], PhaseQualityResult]] = {
    "Classification":        _check_classification,
    "Decomposition":         _check_decomposition,
    "Perspectives":          _check_perspectives,
    "Critique & Pruning":    _check_critique,
    "Stress Testing":        _check_stress_testing,
    "Synthesis":             _check_synthesis,
    "Context Vetting":       _check_context_vetting,
    "Deep Read":             _check_deep_read,
    "Decompose Topic":       _check_decompose_topic,
    "Retrieve Sources":      _check_retrieve_sources,
    "Extract Claims (CoVE)": _check_extract_claims,
    "Final Assembly":        _check_final_assembly,
    "Humanize":              _check_humanize,
    # Brainstorming / VS phases
    "VS Idea Generation":   _check_brainstorm_generate,
    "Cluster & Score":      _check_brainstorm_cluster,
    "Deep Development":     _check_brainstorm_develop,
}


def evaluate_rules(phase_name: str, state: PipelineState) -> PhaseQualityResult:
    """Run rule-based quality check for the given phase. Returns PASS if no rule exists."""
    rule = _RULES.get(phase_name)
    if rule is None:
        return _ok(score=8.0)
    return rule(state)


# ─────────────────────────────────────────────────────────────────────────────
# State reset — clears phase outputs before a retry
# ─────────────────────────────────────────────────────────────────────────────

def _pop_writing(key: str):
    def _reset(state: PipelineState) -> None:
        state.writing_state.pop(key, None)
    return _reset


def _reset_vetted_context(state: PipelineState) -> None:
    setattr(state, "vetted_context", [])
    setattr(state, "context_quality", "unknown")


_RESET: dict[str, Callable[[PipelineState], None]] = {
    "Classification":        lambda s: setattr(s, "task_type", None),
    "Decomposition":         lambda s: setattr(s, "decomposition", None),
    "Perspectives":          lambda s: setattr(s, "candidates", []),
    "Critique & Pruning":    lambda s: [setattr(s, "scores", []), setattr(s, "top_candidates", [])],
    "Stress Testing":        lambda s: setattr(s, "stress_results", []),
    "Synthesis":             lambda s: setattr(s, "final_solution", None),
    "Context Vetting":       _reset_vetted_context,
    "Deep Read":             _reset_vetted_context,
    "Decompose Topic":       _pop_writing("subquestions"),
    "Retrieve Sources":      _pop_writing("retrieved_sources"),
    "Extract Claims (CoVE)": _pop_writing("factcheck_reviews"),
    "Final Assembly":        _pop_writing("final_article"),
    "Humanize":              _pop_writing("humanized_article"),
    # Brainstorming / VS phases
    "VS Idea Generation":    lambda s: s.brainstorming_state.clear(),
    "Cluster & Score":       lambda s: [s.brainstorming_state.pop("clusters", None),
                                        s.brainstorming_state.pop("top_ideas", None),
                                        s.brainstorming_state.pop("deduplicated_count", None)],
    "Deep Development":      lambda s: s.brainstorming_state.pop("developments", None),
}


def reset_phase_state(phase_name: str, state: PipelineState) -> None:
    """Clear the outputs written by the given phase so a retry starts clean."""
    reset_fn = _RESET.get(phase_name)
    if reset_fn:
        reset_fn(state)
    # Always clear per-phase token/cost tracking so the retry is measured cleanly
    phase_key_prefix = f"Phase "
    keys_to_clear = [k for k in state.phase_tokens if phase_name in k]
    for k in keys_to_clear:
        state.phase_tokens.pop(k, None)
