"""
Domain core dataclasses extracted from models.py.

Contains: ScenarioType, SubProblem, Assumption, Decomposition,
          SolutionCandidate, CritiqueScore, ReviewHypothesis, StressTestResult,
          MetaCognitiveAudit, GenerationCandidate, CriticDimensionScore,
          CriticScore, VerificationResult, MetaEvaluation, FinalSolution
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields as dc_fields
from enum import Enum
from typing import Any

from reasoner.domain.models import TaskType, ClaimLabel, PerspectiveType, PerspectiveRegistry

class ScenarioType(str, Enum):
    OPTIMAL = "optimal"
    CONSTRAINT_VIOLATION = "constraint_violation"
    ADVERSARIAL = "adversarial"

    @classmethod
    def coerce(cls, value: str | "ScenarioType") -> "ScenarioType":
        """Accept enum values, enum names, and common separator variants.
        Unknown scenario names returned by the LLM gracefully fall back to
        ADVERSARIAL so that stress-test results are not silently discarded.
        """
        if isinstance(value, cls):
            return value
        raw = str(value).strip()
        try:
            return cls(raw)
        except ValueError:
            normalized = raw.lower().replace("-", "_").replace(" ", "_")
            member = cls.__members__.get(normalized.upper())
            if member is not None:
                return member
            return cls.ADVERSARIAL


@dataclass
class SubProblem:
    id: str
    description: str
    inputs: list[str]
    outputs: list[str]
    constraints: list[str]


@dataclass
class Assumption:
    text: str
    label: ClaimLabel
    rationale: str = ""
    source_hint: str = ""


@dataclass
class Decomposition:
    sub_problems: list[SubProblem]
    assumptions: list[Assumption]
    failure_modes: list[str]
    # raw_response is only populated when explicitly saved by the pipeline.
    # Default "" so _from_dict can filter unknown LLM keys without crashing.
    raw_response: str = ""
    critical_sources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SolutionCandidate:
    perspective: PerspectiveType | str
    content: str
    key_insights: list[str]
    model_used: str

    def __post_init__(self) -> None:
        if isinstance(self.perspective, str):
            self.perspective = PerspectiveRegistry.coerce(self.perspective)


@dataclass
class CritiqueScore:
    perspective: PerspectiveType | str
    logical_consistency: float       # 0-10
    evidence_support: float          # 0-10
    failure_resilience: float        # 0-10
    feasibility: float               # 0-10
    bias_flags: list[str]
    steel_man: str                   # strongest charitable interpretation (best case FOR the candidate)
    # Penalises overconfident-but-wrong claims; sourced from the critique prompt.
    # Default 0.0 so deserialized CritiqueScores without this field still load cleanly.
    confidence_vs_accuracy_penalty: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.perspective, str):
            self.perspective = PerspectiveRegistry.coerce(self.perspective)

    @property
    def total(self) -> float:
        base = (
            self.logical_consistency
            + self.evidence_support
            + self.failure_resilience
            + self.feasibility
        ) / 4.0
        return max(0.0, base - self.confidence_vs_accuracy_penalty)


@dataclass
class ReviewHypothesis:
    """One independent failure hypothesis from Verbalized-Sampling critique.

    Unlike CritiqueScore (which rates each perspective candidate), a hypothesis
    is a distinct, probability-ranked suspected flaw spanning the whole solution
    set. Forcing the critic to verbalize a *distribution* of non-overlapping
    hypotheses — each with falsifying evidence and a concrete check — counters
    the "looks good overall" mode collapse of single-path review.

    All fields carry defaults so older state files (which lack this block)
    deserialize cleanly on --resume.
    """
    claim: str = ""                  # the suspected flaw / risk
    probability: float = 0.0         # 0.0-1.0 self-estimated likelihood it is real
    severity: str = "LOW"            # "HIGH" | "MED" | "LOW"
    evidence_for: str = ""           # what supports the hypothesis
    evidence_against: str = ""       # what argues against it
    verification: str = ""           # concrete test/check to confirm or falsify
    cost_if_wrong: str = ""          # impact if shipped uncaught


@dataclass
class EvidenceBundle:
    """Provenance bundle linking a claim to its supporting evidence.

    All-default fields for ``--resume`` backward compatibility.

    Source tiers:
      - "sensor": backed by a deterministic check (#1 executor, search, test)
      - "model": asserted by an LLM with no external verification
      - "search": grounded in retrieved web/document context
    """
    label: str = "UNKNOWN"                         # mirrors ClaimLabel
    checks_run: list[str] = field(default_factory=list)     # "executed: exit 0"
    evidence_refs: list[str] = field(default_factory=list)  # execution_evidence_ids, source URLs
    untested: str = ""                             # what hasn't been checked
    residual_risk: str = ""                        # remaining risk despite checks
    source: str = "model"                          # "model" | "sensor" | "search"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "checks_run": self.checks_run,
            "evidence_refs": self.evidence_refs,
            "untested": self.untested,
            "residual_risk": self.residual_risk,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceBundle":
        return cls(
            label=data.get("label", "UNKNOWN"),
            checks_run=data.get("checks_run") or [],
            evidence_refs=data.get("evidence_refs") or [],
            untested=data.get("untested", ""),
            residual_risk=data.get("residual_risk", ""),
            source=data.get("source", "model"),
        )


@dataclass
class PlanContract:
    """Inspectable plan contract for the Coding method (#5).

    All-default fields for ``--resume`` backward compatibility.
    """
    targets: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    rollback_points: list[str] = field(default_factory=list)
    risky_ops: list[str] = field(default_factory=list)
    read_set: list[str] = field(default_factory=list)
    write_set: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "targets": self.targets,
            "invariants": self.invariants,
            "validation_commands": self.validation_commands,
            "rollback_points": self.rollback_points,
            "risky_ops": self.risky_ops,
            "read_set": self.read_set,
            "write_set": self.write_set,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanContract":
        return cls(
            targets=list(data.get("targets") or []),
            invariants=list(data.get("invariants") or []),
            validation_commands=list(data.get("validation_commands") or []),
            rollback_points=list(data.get("rollback_points") or []),
            risky_ops=list(data.get("risky_ops") or []),
            read_set=list(data.get("read_set") or []),
            write_set=list(data.get("write_set") or []),
        )


@dataclass
class StressTestResult:
    scenario: ScenarioType
    survival_rate: float             # 0.0 - 1.0
    failure_mode: str = ""
    recovery_path: str = ""


@dataclass
class MetaCognitiveAudit:
    most_dangerous_assumption: str
    dominant_bias: str
    remaining_uncertainty: str
    assumption_failure_impact: str
    non_obvious_insight: str


@dataclass
class GenerationCandidate:
    """A candidate solution generated by one of the 3 independent generators."""
    generator_id: str         # "generator_1", "generator_2", "generator_3"
    model_used: str           # actual model name
    solution: str             # full solution text
    confidence: float         # 0.0-1.0 self-assessed
    key_claims: list[str]     # verifiable claims
    approach_summary: str     # 1-2 sentence summary


@dataclass
class CriticDimensionScore:
    """Score for one candidate across one critic's 4 dimensions."""
    factuality: float         # 0-10
    reasoning: float          # 0-10
    completeness: float       # 0-10
    helpfulness: float        # 0-10
    # Penalises overconfident-but-wrong claims
    confidence_vs_accuracy_penalty: float = 0.0

    @property
    def total(self) -> float:
        base = (self.factuality + self.reasoning + self.completeness + self.helpfulness) / 4.0
        return max(0.0, base - self.confidence_vs_accuracy_penalty)


@dataclass
class CriticScore:
    """Scores from one critic evaluating all 3 generator candidates."""
    critic_id: str            # "critic_1", "critic_2", "critic_3"
    critic_model: str
    candidate_scores: dict[str, CriticDimensionScore]  # generator_id → scores
    ranking: list[str]        # generator_ids best→worst
    dissenting_note: str


@dataclass
class VerificationResult:
    """Result of verifying a claim from a generator."""
    claim: str
    source_generator: str
    verdict: ClaimLabel       # VERIFIED / HYPOTHESIS / UNKNOWN
    evidence: str
    confidence: float         # 0.0-1.0


@dataclass
class MetaEvaluation:
    """Meta-evaluation of the critics themselves (judge-the-judges)."""
    critic_reliability: dict[str, float]  # critic_id → reliability 0-10
    bias_analysis: dict[str, str]         # critic_id → bias description
    agreement_rate: float                  # 0.0-1.0
    most_reliable_critic: str
    least_reliable_critic: str
    meta_insight: str


@dataclass
class FinalSolution:
    core_solution: str
    critical_insights: list[str]     # max 5, non-obvious only
    action_blueprint: list[dict[str, Any]]
    open_questions: list[str]
    claim_labels: dict[str, ClaimLabel]
    meta_audit: MetaCognitiveAudit
    sources: list[dict[str, str]] = field(default_factory=list)  # Citation sources: [{"title": "...", "url": "..."}]
    layout_hints: dict[str, Any] = field(default_factory=dict) # Presentation hints: color, layout type
    # ORCHESTRATED method fields
    generator_attribution: dict[str, str] = field(default_factory=dict)  # generator_id → contribution summary
    critic_weighting: dict[str, float] = field(default_factory=dict)  # critic_id → weight based on reliability
    # Post-synthesis cross-model verification audit
    verification_audit: dict[str, Any] = field(default_factory=dict)
    # Evidence bundles per claim (keyed by claim text, value = EvidenceBundle)
    evidence: dict[str, EvidenceBundle] = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1 — Immutable domain types for the Article pipeline
# ═════════════════════════════════════════════════════════════════════════════

from dataclasses import replace as _replace
from typing import Generic, TypeVar, Union as _Union
import re

_T = TypeVar("_T")
_E = TypeVar("_E")


# ── Phase 2: Canonical Verdict taxonomy ──────────────────────────────

class Verdict(str, Enum):
    """One canonical verdict taxonomy for the entire pipeline.

    Collapses three pre-existing ad-hoc verdict systems into one:
      - verified_claims[].verdict (3-value: supported|unsupported|partially_supported)
      - claim_ledger[].status    (4-value: verified|supported|speculative|unsupported)
      - ClaimLabel enum          (3-value: VERIFIED|HYPOTHESIS|UNKNOWN)
    """
    VERIFIED = "verified"           # verbatim / direct source match
    SUPPORTED = "supported"         # entailed by source, reworded
    PARTIAL = "partial"             # some support, incomplete
    SPECULATIVE = "speculative"     # opinion / hypothesis / unverifiable
    UNSUPPORTED = "unsupported"     # no source found


def map_verdict(raw: object, is_opinion: bool = False) -> Verdict:
    """Normalise any raw LLM verdict string to the canonical ``Verdict``.

    Handles all three pre-existing verdict taxonomies plus common
    misspellings and variants.  Returns ``Verdict.UNSUPPORTED`` as a
    safe default for unrecognised strings.
    """
    if is_opinion:
        return Verdict.SPECULATIVE

    # Handle enum/object inputs
    if isinstance(raw, Verdict):
        return raw
    if hasattr(raw, "value"):
        raw = raw.value
    if not isinstance(raw, str):
        return Verdict.UNSUPPORTED

    raw_lower = raw.lower().strip()

    # From the ClaimLabel enum
    if raw_lower in ("verified", "verifiable", "confirmed", "cross-checked"):
        return Verdict.VERIFIED

    # From verified_claims[].verdict (3-value prompt) and claim_ledger[].status (4-value prompt)
    if raw_lower in ("supported", "entailed"):
        return Verdict.SUPPORTED
    if raw_lower in ("partial", "partially_supported", "partially supported"):
        return Verdict.PARTIAL

    # Speculative / unverifiable
    if raw_lower in ("speculative", "opinion", "hypothesis", "unverifiable"):
        return Verdict.SPECULATIVE

    # From the ClaimLabel enum plus variants
    if raw_lower in ("unsupported", "unsubstantiated", "unconfirmed", "unknown", "false", "refuted"):
        return Verdict.UNSUPPORTED

    # Unknown → safe default
    return Verdict.UNSUPPORTED


# ── Phase 2: Pure functions for the living ledger ────────────────────

def claim_support_ratio(claims: tuple[Claim, ...]) -> float:
    """Honest support ratio where partial counts as 0.5, not 0.

    Matches the plan's fix for G3 (taxonomy inconsistency / lossy ratio).
    """
    # Consider only non-speculative claims
    factual = [c for c in claims if c.verdict not in (Verdict.SPECULATIVE,)]
    if not factual:
        return 0.0

    weighting = {
        Verdict.VERIFIED: 1.0,
        Verdict.SUPPORTED: 1.0,
        Verdict.PARTIAL: 0.5,
        Verdict.UNSUPPORTED: 0.0,
    }
    score = sum(weighting.get(c.verdict, 0.0) for c in factual)
    return score / len(factual)


def compute_locked_spans(markdown: str, claims: tuple[Claim, ...]) -> tuple[tuple[int, int], ...]:
    """Compute character spans of VERIFIED and SUPPORTED claims.

    Only VERIFIED and SUPPORTED claims lock text — PARTIAL, SPECULATIVE,
    and UNSUPPORTED claims do not protect their text from editing.

    Finds **all** occurrences of each claim text in the markdown
    (not just the first), so repeated key claims are all protected.
    """
    spans: list[tuple[int, int]] = []
    for c in claims:
        if c.verdict in (Verdict.VERIFIED, Verdict.SUPPORTED) and c.text:
            # Find ALL occurrences, not just the first
            start = 0
            while True:
                idx = markdown.find(c.text, start)
                if idx < 0:
                    break
                spans.append((idx, idx + len(c.text)))
                start = idx + 1
    return tuple(sorted(spans))


def verify_locked_spans(original: str, edited: str, spans: tuple[tuple[int, int], ...]) -> bool:
    """Check that text within locked spans has not been altered.

    Returns ``True`` if every locked span's text still appears in ``edited``.
    A simple substring check is sufficient for Phase 2 — full position-level
    alignment is deferred.
    """
    for start, end in spans:
        original_text = original[start:end]
        if not original_text or original_text not in edited:
            return False
    return True


def _extract_claim_candidates(markdown: str) -> list[str]:
    """Simple sentence-split to extract candidate claim text from markdown.

    For v1 this is intentionally naive (split on ``. `` + ``? `` + ``! ``)
    and strips markdown formatting.  Phase 3 can improve extraction.
    """
    import re as _re
    # Strip common markdown
    text = markdown
    text = _re.sub(r"#{1,6}\s+", "", text)      # headings
    text = _re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)  # bold/italic
    text = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = _re.sub(r"`[^`]+`", "", text)         # inline code

    sentences = _re.split(r"(?<=[.!?])\s+", text)
    # Filter to reasonably substantial sentences (>= 8 chars, single words excluded)
    return [s.strip() for s in sentences if len(s.strip()) >= 8]


def reconcile_ledger(
    prev_claims: tuple[Claim, ...],
    new_doc: WritingDocument,
) -> tuple[tuple[Claim, ...], list[str]]:
    """Reconcile a claim ledger against a new document version.

    Returns
    -------
    carried : tuple[Claim, ...]
        Claims whose text is still present in ``new_doc``, re-anchored to
        the new version.  Claims whose text vanished are dropped.
    to_verify : list[str]
        Text segments in ``new_doc`` that have no corresponding claim in
        the carried ledger — these need re-verification.
    """
    prev_texts: set[str] = set()
    carried: list[Claim] = []

    for c in prev_claims:
        if c.text and c.text.strip().lower() in new_doc.markdown.lower():
            # Re-anchor to current version
            carried.append(_replace(c, verified_against_version=new_doc.version))
            # Store both with and without trailing period for matching
            ct = c.text.strip().lower()
            prev_texts.add(ct)
            prev_texts.add(ct.rstrip("."))
            prev_texts.add(ct + ".")

    # Find new text not yet claimed
    candidates = _extract_claim_candidates(new_doc.markdown)
    to_verify = [
        cand for cand in candidates
        if cand.strip().lower().rstrip(".") not in prev_texts
    ]

    return tuple(carried), to_verify


# re-export old alias for backward compatibility
VerdictMap = map_verdict


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5 — Additive event log (provenance channel)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ArticleEvent:
    """An immutable log entry recording one significant pipeline event.

    Events are appended to ``ArticleContext.events`` and represent a cheap,
    append-only provenance channel.  They are NOT the control flow — they
    are additive observability for debugging, audit trails, and the UI.
    """
    phase: str = ""
    event: str = ""
    summary: str = ""
    details: dict = field(default_factory=dict)
    timestamp: float = 0.0


def make_article_event(phase: str, event: str, summary: str,
                       details: dict | None = None) -> ArticleEvent:
    """Create an ArticleEvent with auto-timestamp."""
    import time as _time
    return ArticleEvent(
        phase=phase,
        event=event,
        summary=summary[:200],  # cap length
        details=details or {},
        timestamp=_time.monotonic(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3 — Quality gates & verifier independence
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Threshold:
    """A single quality dimension: name, minimum score, and relative weight."""
    dimension: str
    min_value: float = 0.6
    weight: float = 1.0


@dataclass(frozen=True)
class GatePolicy:
    """Weighted quality gates evaluated against audit results.

    Usage::

        policy = GatePolicy((
            Threshold("claim_support", 0.75, 3.0),
            Threshold("citation_accuracy", 0.80, 3.0),
        ))
        passes, details = policy.evaluate(audit_data)
    """
    thresholds: tuple[Threshold, ...] = ()

    def evaluate(self, audit: dict) -> tuple[bool, dict]:
        """Evaluate audit data against this policy.

        Returns
        -------
        passes : bool
            ``True`` if all hard minima are met AND the weighted score >= 0.6.
        details : dict
            ``{"score": float, "hard_ok": bool, "failures": list[str]}``
        """
        failures: list[str] = []
        weighted_sum = 0.0
        total_weight = 0.0

        for t in self.thresholds:
            actual = audit.get(t.dimension, 0.0)
            if not isinstance(actual, (int, float)):
                actual = 0.0
            weighted_sum += actual * t.weight
            total_weight += t.weight
            if actual < t.min_value:
                failures.append(t.dimension)

        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        hard_ok = len(failures) == 0
        passes = hard_ok and score >= 0.6

        return passes, {"score": round(score, 4), "hard_ok": hard_ok, "failures": failures}


# ── Per-content-class gate policies ───────────────────────────────────
# Trust dimensions weigh more and floor higher than prose dimensions.

_TRUST_FIRST = GatePolicy((
    Threshold("claim_support",        0.75, 3.0),
    Threshold("citation_accuracy",    0.80, 3.0),
    Threshold("internal_consistency", 0.65, 2.0),
    Threshold("thesis_advancement",   0.60, 1.0),
    Threshold("transition_quality",   0.55, 1.0),
    Threshold("redundancy_removed",   0.55, 1.0),
    Threshold("policy_compliance",    0.90, 2.0),
))

_BALANCED = GatePolicy((
    Threshold("claim_support",        0.65, 2.0),
    Threshold("citation_accuracy",    0.70, 2.0),
    Threshold("thesis_advancement",   0.60, 2.0),
    Threshold("transition_quality",   0.60, 2.0),
    Threshold("redundancy_removed",   0.60, 2.0),
    Threshold("internal_consistency", 0.60, 2.0),
    Threshold("policy_compliance",    0.80, 2.0),
))

GATE_POLICIES: dict[str, GatePolicy] = {
    "greek_briefing":   _TRUST_FIRST,
    "policy_brief":     _TRUST_FIRST,
    "news_analysis":    _TRUST_FIRST,
    "technical":        _TRUST_FIRST,
    "explainer":        _BALANCED,
    "op_ed":            _BALANCED,
    "blog":             _BALANCED,
}

DEFAULT_GATE_POLICY: GatePolicy = GatePolicy((
    Threshold("claim_support",        0.60, 3.0),
    Threshold("citation_accuracy",    0.60, 3.0),
    Threshold("internal_consistency", 0.60, 2.0),
    Threshold("thesis_advancement",   0.50, 1.0),
))


def route_verifier(
    drafter: str,
    critic: str,
    verifier: str,
    synthesis: str,
    factcheck: str = "",
) -> str:
    """Verify that the article verifier is from a different provider family
    than the drafter, critic, factcheck, and synthesis models.

    This is a *validation* function — it raises ``ValueError`` if the
    current preset violates the independence invariant.

    Raises
    ------
    ValueError
        If verifier shares a provider family with any verboten role.
    """
    _families = {"anthropic", "openai", "google", "deepseek", "qwen",
                 "x-ai", "perplexity", "mistral", "tencent", "meta",
                 "moonshot", "z-ai", "minimax", "poolside", "nvidia",
                 "bytedance", "stepfun", "inclusionai", "arcee",
                 "nousresearch", "ollama", "xiaomi"}

    def _family(mid: str) -> str:
        """Heuristic provider family from a model shorthand."""
        mid_l = mid.lower()
        known = {
            "claude": "anthropic", "gpt": "openai", "o1": "openai", "o3": "openai",
            "o4": "openai", "gemini": "google", "deepseek": "deepseek",
            "qwen": "qwen", "grok": "x-ai", "sonar": "perplexity",
            "hy": "tencent", "kimi": "moonshot", "glm": "z-ai",
            "mistral": "mistral", "laguna": "poolside", "llama": "meta",
            "nemotron": "nvidia", "seed": "bytedance", "stepfun": "stepfun",
            "ring": "inclusionai", "ling": "inclusionai", "hermes": "nousresearch",
            "mimo": "xiaomi", "minimax": "minimax", "codestral": "mistral",
            "ministral": "mistral", "arcee": "arcee",
        }
        for prefix, family in known.items():
            if mid_l.startswith(prefix):
                return family
        if "/" in mid_l:
            vendor = mid_l.split("/")[0]
            if vendor in _families:
                return vendor
        return "unknown"

    vf = _family(verifier)
    verboten = {_family(drafter), _family(critic), _family(synthesis)}
    if factcheck:
        verboten.add(_family(factcheck))

    if vf in verboten and vf != "unknown":
        raise ValueError(
            f"Verifier family '{vf}' (model={verifier}) conflicts with "
            f"verboten roles: {verboten}"
        )
    return vf


@dataclass(frozen=True)
class Ok(Generic[_T]):
    """Successful phase result carrying the updated context."""
    value: _T


@dataclass(frozen=True)
class Err(Generic[_E]):
    """Failed phase result with optional degraded fallback."""
    error: _E
    phase: str = ""
    fallback: object | None = None


# Result = Ok[T] | Err[E]  — use via isinstance() checks


@dataclass(frozen=True)
class WritingDocument:
    """The article artifact. Immutable — every edit produces a new instance.

    Carries a version counter and a ``produced_by`` tag so downstream phases
    can always tell which revision they are working with.
    """
    version: int = 0
    markdown: str = ""
    title: str = ""
    produced_by: str = ""           # phase name that generated this revision
    locked_spans: tuple[tuple[int, int], ...] = ()  # char spans of VERIFIED/SUPPORTED claims


@dataclass(frozen=True)
class Claim:
    """Atomic verified/reviewed claim extracted from the article.

    ``verified_against_version`` records which ``WritingDocument.version``
    this claim was verified against — the core invariant that makes the
    stale-ledger bug structurally impossible: any mismatch between
    ``verified_against_version`` and ``doc.version`` is a visible,
    checkable invariant rather than a silent assumption.
    """
    id: str = ""
    text: str = ""
    verdict: "Verdict" = Verdict.SPECULATIVE
    source_url: str = ""
    note: str = ""
    verified_against_version: int = 0


@dataclass(frozen=True)
class ArticleContext:
    """Immutable context threaded through all article pipeline phases.

    Replaces direct ``state.writing_state[...] = value`` mutation with a
    value that is *replaced* (via ``.replace()``) at each phase boundary.
    The old code path (``to_pipeline_state()``) is preserved so prompt
    builders and serializers — which still read from ``PipelineState`` —
    continue to work unchanged.

    Every field has a sensible default so ``ArticleContext()`` alone is
    sufficient for structural tests.
    """

    # Core identity
    problem: str = ""
    language: str = "English"
    preset_name: str = "article-budget"
    content_class: str = "blog"

    # Article artifacts (immutable — replaced on each phase boundary)
    doc: WritingDocument = field(default_factory=WritingDocument)
    claims: tuple[Claim, ...] = ()

    # Source and analytical data
    sources: tuple[dict, ...] = ()
    source_metadata: tuple[dict, ...] = ()
    outline: tuple[dict, ...] = ()
    argument_map: dict = field(default_factory=dict)
    verification_results: dict = field(default_factory=dict)
    structural_critique: dict = field(default_factory=dict)
    editorial_audit: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    style_brief: dict | None = None
    pre_research_summary: str = ""
    gaps_noted: list[str] = field(default_factory=list)

    # Pipeline metadata carried forward
    errors: tuple[str, ...] = ()
    final_solution: object | None = None  # FinalSolution from synthesis phase
    surface_signals: dict = field(default_factory=dict)  # Quality/status signals for UI (Phase 4)
    events: tuple["ArticleEvent", ...] = ()  # Additive event log (Phase 5)

    def replace(self, **kwargs: object) -> "ArticleContext":
        """Return a new ArticleContext with selected fields replaced."""
        from dataclasses import replace as _dataclass_replace
        return _dataclass_replace(self, **kwargs)

    def to_pipeline_state(self) -> object:
        """Build a lightweight dict-shaped object for prompt builders.

        Returns a minimal object that supports ``state.writing_state.get(key)``
        and ``state.problem`` so existing prompt builders work without changes.
        """
        from reasoner.domain.pipeline_state import PipelineState

        state = PipelineState(
            problem=self.problem,
            language=self.language,
            preset_name=self.preset_name,
            method="article",
        )
        ws = state.writing_state
        ws["final_article"] = self.doc.markdown
        ws["retrieved_sources"] = list(self.sources)
        ws["source_metadata"] = list(self.source_metadata)
        ws["argument_map"] = dict(self.argument_map) if self.argument_map else {}
        ws["outline"] = list(self.outline)
        ws["suggested_title"] = self.doc.title
        ws["verification"] = dict(self.verification_results) if self.verification_results else {}
        ws["claim_ledger"] = [
            {"claim": c.text, "source": c.source_url, "status": c.verdict.value}
            for c in self.claims
        ]
        ws["metrics"] = dict(self.metrics) if self.metrics else {}
        ws["structural_critique"] = dict(self.structural_critique) if self.structural_critique else {}
        ws["editorial_audit"] = dict(self.editorial_audit) if self.editorial_audit else {}
        ws["pre_research_summary"] = self.pre_research_summary
        ws["gaps_noted"] = list(self.gaps_noted)
        if self.style_brief:
            ws["style_brief"] = dict(self.style_brief)
        return state

    def sync_to(self, state: object) -> None:
        """Sync ArticleContext fields back into a PipelineState for serializers."""
        state.writing_state["final_article"] = self.doc.markdown
        state.writing_state["retrieved_sources"] = list(self.sources)
        state.writing_state["source_metadata"] = list(self.source_metadata)
        state.writing_state["argument_map"] = dict(self.argument_map) if self.argument_map else {}
        state.writing_state["outline"] = list(self.outline)
        state.writing_state["suggested_title"] = self.doc.title
        state.writing_state["verification"] = dict(self.verification_results) if self.verification_results else {}
        state.writing_state["claim_ledger"] = [
            {"claim": c.text, "source": c.source_url, "status": c.verdict.value}
            for c in self.claims
        ]
        state.writing_state["metrics"] = dict(self.metrics) if self.metrics else {}
        state.writing_state["structural_critique"] = dict(self.structural_critique) if self.structural_critique else {}
        state.writing_state["editorial_audit"] = dict(self.editorial_audit) if self.editorial_audit else {}
        state.writing_state["pre_research_summary"] = self.pre_research_summary
        state.writing_state["gaps_noted"] = list(self.gaps_noted)
        if self.style_brief:
            state.writing_state["style_brief"] = dict(self.style_brief)
        if self.final_solution is not None:
            state.final_solution = self.final_solution
        if self.surface_signals:
            state.writing_state["surface_signals"] = dict(self.surface_signals)
        if self.events:
            state.writing_state["article_events"] = [
                {"phase": e.phase, "event": e.event, "summary": e.summary,
                 "details": e.details, "timestamp": round(e.timestamp, 3)}
                for e in self.events
            ]


# re-export legacy names so the module signature doesn't change
__all__ = [
    "ScenarioType", "SubProblem", "Assumption", "Decomposition",
    "SolutionCandidate", "CritiqueScore", "ReviewHypothesis",
    "StressTestResult", "MetaCognitiveAudit", "GenerationCandidate",
    "CriticDimensionScore", "CriticScore", "VerificationResult",
    "MetaEvaluation", "FinalSolution", "EvidenceBundle", "PlanContract",
    "Ok", "Err", "WritingDocument", "Claim", "ArticleContext",
    "Verdict", "map_verdict", "claim_support_ratio",
    "compute_locked_spans", "verify_locked_spans", "reconcile_ledger",
    "Threshold", "GatePolicy", "GATE_POLICIES", "DEFAULT_GATE_POLICY", "route_verifier",
    "ArticleEvent", "make_article_event",
]


