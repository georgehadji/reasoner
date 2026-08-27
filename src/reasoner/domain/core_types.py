"""
Domain core dataclasses extracted from models.py.

Contains: ScenarioType, SubProblem, Assumption, Decomposition,
          SolutionCandidate, CritiqueScore, ReviewHypothesis, StressTestResult,
          MetaCognitiveAudit, GenerationCandidate, CriticDimensionScore,
          CriticScore, VerificationResult, MetaEvaluation, FinalSolution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from reasoner.domain.models import ClaimLabel, PerspectiveRegistry, PerspectiveType


class ScenarioType(str, Enum):
    OPTIMAL = "optimal"
    CONSTRAINT_VIOLATION = "constraint_violation"
    ADVERSARIAL = "adversarial"

    @classmethod
    def coerce(cls, value: str | ScenarioType) -> ScenarioType:
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
    # W2 premise audit (docs/plans/sycophancy-mitigation.md) — origin distinguishes
    # what the model introduced from what the user asserted, which is what the
    # destructive perspective and synthesis "what I took on your word" section key on.
    origin: str = "analyst"          # "user_stated" | "user_implied" | "analyst"
    load_bearing: bool = False       # recommendation would change if this were false
    falsifier: str = ""              # what would have to be true for this to be wrong
    resolvable_by: str = ""          # "other_party" | "record" | "observation" | ""


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "checks_run": self.checks_run,
            "evidence_refs": self.evidence_refs,
            "untested": self.untested,
            "residual_risk": self.residual_risk,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceBundle:
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

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> PlanContract:
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


