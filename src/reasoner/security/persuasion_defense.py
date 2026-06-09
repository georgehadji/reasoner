"""
Reasoner Persuasion Defense Module
==================================
Production module for a hallucination mitigation pipeline ("Reasoner") targeting
regulated B2B verticals (radiology CDS, legal contract intelligence,
aerospace/defense).

Insertion point: between ClaimExtractionStage (5) and TwoTierVerificationStage (6).

Architecture: 5-stage pipeline with Pydantic contracts, per-chunk taint
propagation, NLI-before-LLM cost ordering, and conflict surfacing.

Python 3.12 | Type hints | Error handling throughout
"""

import asyncio
import json
import logging
import math
import re
import time
from abc import ABC, abstractmethod
from collections import Counter, deque
from enum import Enum
from typing import Any, Protocol, Self

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


class PersuasionDefenseConfig(BaseModel):
    """Configurable thresholds and weights for the persuasion defense pipeline."""

    nli_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    coverage_floor: float = Field(default=0.6, ge=0.0, le=1.0)
    drift_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    friction_weight_coverage: float = Field(default=0.4, ge=0.0, le=1.0)
    friction_weight_tactics: float = Field(default=0.35, ge=0.0, le=1.0)
    friction_weight_drift: float = Field(default=0.25, ge=0.0, le=1.0)
    behavioral_rolling_window: int = Field(default=100, ge=1)
    llm_escalation_cap: int = Field(default=5, ge=0)
    max_probe_variants: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def check_weights_sum(self) -> Self:
        total = (
            self.friction_weight_coverage
            + self.friction_weight_tactics
            + self.friction_weight_drift
        )
        if not math.isclose(total, 1.0, rel_tol=1e-6):
            raise ValueError(f"Friction weights must sum to 1.0, got {total}")
        return self


# =============================================================================
# ENUMS & DOMAIN TYPES
# =============================================================================


class PersuasionTactic(str, Enum):
    URGENCY_FABRICATION = "urgency_fabrication"
    SOCIAL_PROOF_INJECTION = "social_proof_injection"
    AUTHORITY_SPOOFING = "authority_spoofing"
    EMOTIONAL_LOADING = "emotional_loading"
    COMMITMENT_ESCALATION = "commitment_escalation"
    FRAMING_ASYMMETRY = "framing_asymmetry"


class FrictionAction(str, Enum):
    PASS = "pass"
    ANNOTATE = "annotate"
    ATTENUATE = "attenuate"
    BLOCK = "block"


# =============================================================================
# PYDANTIC INTERFACE CONTRACTS
# =============================================================================


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    source_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedClaim(BaseModel):
    claim_id: str
    claim_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaintRecord(BaseModel):
    """Single taint event in the audit trail."""

    source: str
    stage: str
    timestamp: float = Field(default_factory=time.time)
    severity: float = Field(ge=0.0, le=1.0)
    detail: str
    chunk_id: str | None = None
    claim_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_severity_finite(self) -> Self:
        if not math.isfinite(self.severity):
            raise ValueError(f"Severity must be finite, got {self.severity}")
        return self


class CoverageReport(BaseModel):
    """Output of Stage 1: CoverageAuditStage."""

    total_claims: int
    supported_claims: int
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[ExtractedClaim] = Field(default_factory=list)
    claim_taints: list[TaintRecord] = Field(default_factory=list)
    pipeline_taint: TaintRecord | None = None


class TacticReport(BaseModel):
    """Output of Stage 2: TacticDetectionStage."""

    tactic_count: int
    tactic_scores: dict[str, float] = Field(default_factory=dict)
    taints: list[TaintRecord] = Field(default_factory=list)
    detected_spans: list[dict[str, Any]] = Field(default_factory=list)


class IntentConsistencyReport(BaseModel):
    """Output of Stage 3: IntentConsistencyStage."""

    drift_score: float = Field(ge=0.0, le=1.0)
    escalation_triggered: bool
    explanation: str | None = None
    taint: TaintRecord | None = None


class FrictionDecision(BaseModel):
    """Output of Stage 4: ActiveFrictionGate."""

    action: FrictionAction
    risk_score: float = Field(ge=0.0, le=1.0)
    conflict_points: list[str] = Field(default_factory=list)
    recommended_rewrites: list[str] | None = Field(default=None)


class BehavioralAuditReport(BaseModel):
    """Output of Stage 5: BehavioralAuditStage."""

    coverage_trend: float = 0.0
    tactic_histogram: dict[str, int] = Field(default_factory=dict)
    escalation_count: int = 0
    action_histogram: dict[str, int] = Field(default_factory=dict)
    taint: TaintRecord | None = None


class PersuasionDefenseResult(BaseModel):
    """Aggregated output of the full 5-stage persuasion defense pipeline."""

    coverage: CoverageReport
    tactics: TacticReport
    intent_consistency: IntentConsistencyReport
    friction: FrictionDecision
    behavioral_audit: BehavioralAuditReport | None = None
    overall_risk_score: float = Field(ge=0.0, le=1.0)
    all_taints: list[TaintRecord] = Field(default_factory=list)
    pipeline_latency_ms: float = 0.0


# =============================================================================
# ABSTRACT INTERFACES (Dependency Injection)
# =============================================================================


class NLIClassifier(Protocol):
    """Protocol for NLI-based verification (DeBERTa-v3-large in production)."""

    async def classify(self, premise: str, hypothesis: str) -> tuple[str, float]:
        """Returns (label, confidence) where label ∈ {entailment, contradiction, neutral}."""
        ...


class LLMVerifier(Protocol):
    """Protocol for LLM-based verification."""

    async def verify(self, prompt: str, max_tokens: int = 512) -> str:
        ...


class EmbeddingModel(Protocol):
    """Protocol for text embedding (used in intent consistency)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class ModelRegistry(Protocol):
    """Registry abstraction for structured LLM calls."""

    async def call(
        self, prompt: str, max_tokens: int = 256, json_mode: bool = True
    ) -> dict[str, Any]:
        ...


# =============================================================================
# STAGE IMPLEMENTATIONS
# =============================================================================


class PersuasionDefenseStage(ABC):
    """
    Base class for all persuasion defense stages.
    """

    def __init__(self, config: PersuasionDefenseConfig) -> None:
        self.config = config

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> BaseModel:
        ...


# ---------------------------------------------------------------------------
# STAGE 1: CoverageAuditStage
# ---------------------------------------------------------------------------


class CoverageAuditStage(PersuasionDefenseStage):
    """
    Measures whether extracted claims are supported by the retrieval set.
    Flags unsupported claims and emits pipeline-level taint when coverage
    falls below the configured floor.
    """

    async def execute(
        self,
        retrieval_set: list[RetrievedChunk],
        extracted_claims: list[ExtractedClaim],
        nli: NLIClassifier,
    ) -> CoverageReport:
        total_claims = len(extracted_claims)
        if total_claims == 0:
            return CoverageReport(
                total_claims=0, supported_claims=0, coverage_ratio=1.0
            )

        supported_claims = 0
        unsupported_claims: list[ExtractedClaim] = []
        claim_taints: list[TaintRecord] = []

        for claim in extracted_claims:
            best_score = 0.0
            for chunk in retrieval_set:
                try:
                    label, score = await nli.classify(
                        premise=chunk.content,
                        hypothesis=claim.claim_text,
                    )
                    if label == "entailment" and score > best_score:
                        best_score = score
                except Exception as e:
                    logger.warning(
                        f"NLI classification failed for claim {claim.claim_id}: {e}"
                    )
                    continue

            if best_score > self.config.nli_threshold:
                supported_claims += 1
            else:
                unsupported_claims.append(claim)
                claim_taints.append(
                    TaintRecord(
                        source="coverage_audit",
                        stage="coverage_audit",
                        severity=0.6,
                        detail=(
                            f"Claim has ZERO retrieval support "
                            f"(best NLI score {best_score:.3f})."
                        ),
                        claim_id=claim.claim_id,
                        evidence={
                            "best_nli_score": best_score,
                            "claim_text": claim.claim_text,
                        },
                    )
                )

        coverage_ratio = (
            supported_claims / total_claims if total_claims > 0 else 1.0
        )

        pipeline_taint: TaintRecord | None = None
        if coverage_ratio < self.config.coverage_floor:
            pipeline_taint = TaintRecord(
                source="coverage_audit",
                stage="coverage_audit",
                severity=0.9,  # HIGH
                detail=(
                    f"Coverage ratio {coverage_ratio:.3f} below floor "
                    f"{self.config.coverage_floor:.3f}. "
                    f"Unsupported claims: "
                    f"{len(unsupported_claims)}/{total_claims}"
                ),
                evidence={
                    "coverage_ratio": coverage_ratio,
                    "coverage_floor": self.config.coverage_floor,
                    "unsupported_count": len(unsupported_claims),
                },
            )

        return CoverageReport(
            total_claims=total_claims,
            supported_claims=supported_claims,
            coverage_ratio=coverage_ratio,
            unsupported_claims=unsupported_claims,
            claim_taints=claim_taints,
            pipeline_taint=pipeline_taint,
        )


# ---------------------------------------------------------------------------
# STAGE 2: TacticDetectionStage
# ---------------------------------------------------------------------------

PERSUASION_PATTERNS: dict[PersuasionTactic, list[re.Pattern[str]]] = {
    PersuasionTactic.URGENCY_FABRICATION: [
        re.compile(
            r"\b(act\s+(?:now|fast|quickly)|limited\s+(?:time|offer|availability))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(don'?t\s+miss\s+(?:out|this)|before\s+it'?s?\s+(?:too\s+late|gone))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(only\s+(?:a\s+few|limited)\s+(?:left|spots?|spaces?))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(expires?\s+(?:soon|today|tomorrow))\b",
            re.IGNORECASE,
        ),
    ],
    PersuasionTactic.SOCIAL_PROOF_INJECTION: [
        re.compile(
            r"\b(everyone\s+(?:is\s+buying|loves?|agrees?))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(join\s+(?:thousands|millions|countless))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(most\s+popular|best-?selling|top\s+rated)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(highly\s+recommended\s+by|users\s+love)\b",
            re.IGNORECASE,
        ),
    ],
    PersuasionTactic.AUTHORITY_SPOOFING: [
        re.compile(
            r"\b(experts?\s+(?:agree|say|recommend|confirm))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(studies?\s+(?:show|prove|confirm))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(doctors?\s+(?:recommend|agree|say))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(according\s+to\s+(?:leading|top|renowned))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(it\s+is\s+widely\s+(?:accepted|known|recognized))\b",
            re.IGNORECASE,
        ),
    ],
    PersuasionTactic.EMOTIONAL_LOADING: [
        re.compile(
            r"\b(life-?changing|transform\s+(?:your|the)|revolutionary)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(imagine\s+(?:how|the|what))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(you\s+(?:deserve|owe\s+it\s+to\s+yourself))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(feel\s+(?:amazing|incredible|fantastic))\b",
            re.IGNORECASE,
        ),
    ],
    PersuasionTactic.COMMITMENT_ESCALATION: [
        re.compile(
            r"\b(just\s+(?:try|start|click|say))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(start\s+with\s+a\s+small\s+step)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(you(?:'ve| have)\s+already\s+(?:decided|committed))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(take\s+the\s+next\s+step|commit\s+now)\b",
            re.IGNORECASE,
        ),
    ],
    PersuasionTactic.FRAMING_ASYMMETRY: [
        re.compile(
            r"\b(obviously|clearly|undeniably|unquestionably)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(the\s+(?:only|obvious|clear)\s+(?:choice|answer|solution))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(simple\s+as\s+that|no\s+question)\b",
            re.IGNORECASE,
        ),
    ],
}


class TacticDetectionStage(PersuasionDefenseStage):
    """
    Two-tier persuasion detection following Reasoner's NLI-before-LLM cost ordering.
    Tier 1: Regex pattern matching (fast, no LLM).
    Tier 2: NLI verification of pattern-matched spans (capped).
    """

    NLI_ESCALATION_CAP: int = 20

    def __init__(
        self, config: PersuasionDefenseConfig, nli: NLIClassifier
    ) -> None:
        super().__init__(config)
        self.nli = nli

    async def execute(self, generated_output: str) -> TacticReport:
        pattern_hits = self._pattern_scan(generated_output)
        detected_spans: list[dict[str, Any]] = []
        taints: list[TaintRecord] = []
        tactic_scores: dict[str, float] = {}
        nli_calls = 0

        for hit in pattern_hits:
            if nli_calls >= self.NLI_ESCALATION_CAP:
                hit["confidence"] = hit["pattern_score"]
                hit["detector"] = "pattern_cap_reached"
                detected_spans.append(hit)
                continue

            try:
                hypothesis = (
                    f"This text uses {hit['tactic'].replace('_', ' ')} "
                    f"as a persuasion technique."
                )
                label, score = await self.nli.classify(
                    premise=hit["text_span"],
                    hypothesis=hypothesis,
                )
                nli_calls += 1

                if label == "entailment" and score > 0.6:
                    hit["confidence"] = score
                    hit["detector"] = "nli_verified"
                    detected_spans.append(hit)
                    tactic_scores[hit["tactic"]] = max(
                        tactic_scores.get(hit["tactic"], 0.0), score
                    )
                    taints.append(
                        TaintRecord(
                            source="persuasion_tactic",
                            stage="tactic_detection",
                            severity=min(1.0, score),
                            detail=(
                                f"Detected {hit['tactic']} in span: "
                                f"{hit['text_span'][:80]}..."
                            ),
                            evidence={
                                "tactic": hit["tactic"],
                                "span": hit["text_span"],
                                "span_start": hit["span_start"],
                                "span_end": hit["span_end"],
                                "nli_score": score,
                            },
                        )
                    )
                elif label == "neutral" and score > 0.4:
                    hit["confidence"] = score * 0.7
                    hit["detector"] = "nli_probable"
                    detected_spans.append(hit)
                # If contradiction, drop the detection (pattern false positive)

            except Exception as e:
                logger.warning(
                    f"NLI verification failed for tactic detection: {e}"
                )
                hit["confidence"] = hit["pattern_score"]
                hit["detector"] = "pattern_nli_failed"
                detected_spans.append(hit)

        tactic_count = len(detected_spans)

        return TacticReport(
            tactic_count=tactic_count,
            tactic_scores=tactic_scores,
            taints=taints,
            detected_spans=detected_spans,
        )

    def _pattern_scan(self, text: str) -> list[dict[str, Any]]:
        """Fast regex-based first pass."""
        detections: list[dict[str, Any]] = []
        for tactic, patterns in PERSUASION_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    context_span = text[start:end]
                    detections.append(
                        {
                            "tactic": tactic.value,
                            "text_span": context_span,
                            "span_start": match.start(),
                            "span_end": match.end(),
                            "pattern_score": 0.5,
                            "confidence": 0.0,
                            "detector": "pattern",
                        }
                    )
        return detections


# ---------------------------------------------------------------------------
# STAGE 3: IntentConsistencyStage
# ---------------------------------------------------------------------------


class IntentConsistencyStage(PersuasionDefenseStage):
    """
    Detects persuasive intent instability by generating probe variants of the
    output and comparing semantic drift via embeddings. Escalates to LLM for
    an explanation only when drift exceeds the threshold.
    """

    def __init__(
        self,
        config: PersuasionDefenseConfig,
        embedding_model: EmbeddingModel,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        super().__init__(config)
        self.embedding_model = embedding_model
        self.model_registry = model_registry
        self._escalation_counter = 0

    async def execute(
        self,
        generated_output: str,
        retrieval_set: list[RetrievedChunk],
        probe_variables: dict[str, str] | None,
    ) -> IntentConsistencyReport:
        _ = retrieval_set  # Reserved for future context-aware probing

        if not probe_variables:
            return IntentConsistencyReport(
                drift_score=0.0,
                escalation_triggered=False,
                explanation=None,
                taint=None,
            )

        variants = self._generate_probe_variants(
            generated_output, probe_variables
        )
        if len(variants) < 2:
            return IntentConsistencyReport(
                drift_score=0.0,
                escalation_triggered=False,
                explanation=None,
                taint=None,
            )

        try:
            embeddings = await self.embedding_model.embed(variants)
        except Exception as e:
            logger.error(
                f"Embedding failed for intent consistency: {e}"
            )
            return IntentConsistencyReport(
                drift_score=0.0,
                escalation_triggered=False,
                explanation=None,
                taint=None,
            )

        # Compute average pairwise cosine distance as drift
        sims: list[float] = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sims.append(
                    self._cosine_similarity(embeddings[i], embeddings[j])
                )

        drift_score = (
            1.0 - (sum(sims) / len(sims)) if sims else 0.0
        )

        escalation_triggered = (
            drift_score > self.config.drift_threshold
        )
        explanation: str | None = None
        taint: TaintRecord | None = None

        if escalation_triggered:
            if (
                self.model_registry is not None
                and self._escalation_counter < self.config.llm_escalation_cap
            ):
                self._escalation_counter += 1
                try:
                    prompt = (
                        "The following text was tested with probe variants. "
                        "Semantic drift was detected, suggesting the output "
                        "may be sensitive to persuasive framing. Provide a "
                        "concise explanation. Return ONLY a JSON object with "
                        "a single key 'explanation'.\n\n"
                        f"Original text:\n{generated_output}\n\n"
                        f"Probe variants:\n"
                        + "\n---\n".join(variants)
                    )
                    raw = await self.model_registry.call(
                        prompt, max_tokens=256, json_mode=True
                    )
                    explanation = (
                        raw.get("explanation", "")
                        if isinstance(raw, dict)
                        else None
                    )
                except Exception as e:
                    logger.warning(
                        f"LLM escalation failed for intent consistency: {e}"
                    )
                    explanation = (
                        "LLM escalation failed; drift detected but "
                        "explanation unavailable."
                    )

            taint = TaintRecord(
                source="intent_inconsistency",
                stage="intent_consistency",
                severity=min(1.0, drift_score),
                detail=(
                    f"Semantic drift {drift_score:.3f} exceeds threshold "
                    f"{self.config.drift_threshold:.3f}."
                ),
                evidence={
                    "drift_score": drift_score,
                    "drift_threshold": self.config.drift_threshold,
                    "escalation_triggered": escalation_triggered,
                    "variant_count": len(variants),
                },
            )

        return IntentConsistencyReport(
            drift_score=drift_score,
            escalation_triggered=escalation_triggered,
            explanation=explanation,
            taint=taint,
        )

    def _generate_probe_variants(
        self, text: str, probe_variables: dict[str, str]
    ) -> list[str]:
        """Generate up to N variants by substituting probe variable values."""
        variants = [text]
        idx = 0
        for key, value in probe_variables.items():
            if value in text and len(variants) < self.config.max_probe_variants:
                alt = f"[{key}_alt_{idx}]"
                variant = text.replace(value, alt)
                if variant not in variants:
                    variants.append(variant)
                    idx += 1
            if len(variants) >= self.config.max_probe_variants:
                break

        # Fallback: mutate first numeric token to reach variant count
        if len(variants) < self.config.max_probe_variants:
            numbers = re.findall(r"\d+(?:\.\d+)?", text)
            for num in numbers:
                if len(variants) >= self.config.max_probe_variants:
                    break
                try:
                    n = float(num)
                    alt_num = (
                        str(int(n * 1.1))
                        if n == int(n)
                        else f"{n * 1.1:.2f}"
                    )
                    variant = text.replace(num, alt_num, 1)
                    if variant not in variants:
                        variants.append(variant)
                except ValueError:
                    continue

        return variants[: self.config.max_probe_variants]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# STAGE 4: ActiveFrictionGate
# ---------------------------------------------------------------------------


class ActiveFrictionGate(PersuasionDefenseStage):
    """
    Computes a composite risk score from coverage, tactics, and intent drift,
    then maps it to a friction action.
    """

    async def execute(
        self,
        coverage_report: CoverageReport,
        tactic_report: TacticReport,
        intent_report: IntentConsistencyReport,
    ) -> FrictionDecision:
        coverage_deficit = 1.0 - coverage_report.coverage_ratio
        tactic_density = min(1.0, tactic_report.tactic_count / 5.0)
        drift_score = intent_report.drift_score

        risk = (
            self.config.friction_weight_coverage * coverage_deficit
            + self.config.friction_weight_tactics * tactic_density
            + self.config.friction_weight_drift * drift_score
        )
        risk = max(0.0, min(1.0, risk))

        if risk < 0.3:
            action = FrictionAction.PASS
        elif risk < 0.6:
            action = FrictionAction.ANNOTATE
        elif risk < 0.8:
            action = FrictionAction.ATTENUATE
        else:
            action = FrictionAction.BLOCK

        conflict_points: list[str] = []
        if coverage_report.unsupported_claims:
            conflict_points.append(
                f"Unsupported claims detected: "
                f"{len(coverage_report.unsupported_claims)}"
            )
        if tactic_report.tactic_count > 0:
            conflict_points.append(
                f"Persuasion tactics detected: {tactic_report.tactic_count} "
                f"({', '.join(tactic_report.tactic_scores.keys())})"
            )
        if intent_report.escalation_triggered:
            conflict_points.append(
                f"Intent inconsistency: drift={intent_report.drift_score:.3f}"
            )

        recommended_rewrites: list[str] | None = None
        if action in (FrictionAction.ANNOTATE, FrictionAction.ATTENUATE):
            recommended_rewrites = [
                "Add inline citations for all factual claims.",
                "Flag unsupported claims with epistemic uncertainty language.",
            ]
            if tactic_report.tactic_count > 0:
                recommended_rewrites.append(
                    "Remove or neutralize detected persuasion tactics."
                )
            if intent_report.escalation_triggered:
                recommended_rewrites.append(
                    "Restate objectives explicitly and verify consistency "
                    "across variants."
                )
        elif action == FrictionAction.BLOCK:
            recommended_rewrites = [
                "Return a structured refusal summarizing detected conflicts.",
            ]

        return FrictionDecision(
            action=action,
            risk_score=risk,
            conflict_points=conflict_points,
            recommended_rewrites=recommended_rewrites,
        )


# ---------------------------------------------------------------------------
# STAGE 5: BehavioralAuditStage
# ---------------------------------------------------------------------------


class BehavioralAuditStage(PersuasionDefenseStage):
    """
    Async, non-blocking behavioral audit with rolling window tracking.
    Emits structured JSON audit records via logger.info.
    """

    def __init__(self, config: PersuasionDefenseConfig) -> None:
        super().__init__(config)
        self._coverage_window: deque[float] = deque(
            maxlen=config.behavioral_rolling_window
        )
        self._tactic_window: deque[dict[str, int]] = deque(
            maxlen=config.behavioral_rolling_window
        )
        self._escalation_window: deque[bool] = deque(
            maxlen=config.behavioral_rolling_window
        )
        self._action_window: deque[str] = deque(
            maxlen=config.behavioral_rolling_window
        )

    async def execute(
        self,
        coverage_report: CoverageReport,
        tactic_report: TacticReport,
        intent_report: IntentConsistencyReport,
        friction_decision: FrictionDecision,
    ) -> BehavioralAuditReport:
        # Update rolling windows
        self._coverage_window.append(coverage_report.coverage_ratio)
        self._tactic_window.append(
            dict(Counter(tactic_report.tactic_scores.keys()))
        )
        self._escalation_window.append(intent_report.escalation_triggered)
        self._action_window.append(friction_decision.action.value)

        # Compute aggregates
        coverage_trend = (
            sum(self._coverage_window) / len(self._coverage_window)
            if self._coverage_window
            else 0.0
        )

        tactic_histogram: Counter[str] = Counter()
        for entry in self._tactic_window:
            for tactic, count in entry.items():
                tactic_histogram[tactic] += count

        escalation_count = sum(1 for e in self._escalation_window if e)

        action_histogram: dict[str, int] = {}
        for act in self._action_window:
            action_histogram[act] = action_histogram.get(act, 0) + 1

        # Emit structured audit record
        audit_payload = {
            "timestamp": time.time(),
            "coverage_trend": coverage_trend,
            "tactic_histogram": dict(tactic_histogram),
            "escalation_count": escalation_count,
            "action_histogram": action_histogram,
            "window_size": len(self._coverage_window),
        }
        logger.info(json.dumps(audit_payload))

        # Systemic taint for repeated patterns
        taint: TaintRecord | None = None
        repeated_tactic: str | None = None
        window_len = max(1, len(self._tactic_window))
        for tactic, count in tactic_histogram.items():
            if count >= max(3, window_len // 3):
                repeated_tactic = tactic
                break

        if repeated_tactic:
            taint = TaintRecord(
                source="behavioral_audit",
                stage="behavioral_audit",
                severity=0.75,
                detail=(
                    f"Systemic pattern detected: repeated {repeated_tactic} "
                    f"over last {window_len} requests."
                ),
                evidence={
                    "repeated_tactic": repeated_tactic,
                    "tactic_histogram": dict(tactic_histogram),
                    "window_size": window_len,
                },
            )

        return BehavioralAuditReport(
            coverage_trend=coverage_trend,
            tactic_histogram=dict(tactic_histogram),
            escalation_count=escalation_count,
            action_histogram=action_histogram,
            taint=taint,
        )


# =============================================================================
# PIPELINE ORCHESTRATOR
# =============================================================================


class PersuasionDefensePipeline:
    """
    Orchestrates the 5-stage persuasion defense pipeline.

    Execution order:
    1. CoverageAudit
    2. TacticDetection
    3. IntentConsistency
    4. ActiveFriction
    5. BehavioralAudit (optional, non-blocking)
    """

    def __init__(
        self,
        nli: NLIClassifier,
        embedding_model: EmbeddingModel,
        model_registry: ModelRegistry | None = None,
        config: PersuasionDefenseConfig | None = None,
        run_behavioral_audit: bool = False,
    ) -> None:
        self.config = config or PersuasionDefenseConfig()
        self.nli = nli
        self.embedding_model = embedding_model
        self.model_registry = model_registry
        self.run_behavioral_audit = run_behavioral_audit

        self.coverage_stage = CoverageAuditStage(self.config)
        self.tactic_stage = TacticDetectionStage(self.config, nli)
        self.intent_stage = IntentConsistencyStage(
            self.config, embedding_model, model_registry
        )
        self.friction_gate = ActiveFrictionGate(self.config)
        self.behavioral_stage: BehavioralAuditStage | None = None
        if run_behavioral_audit:
            self.behavioral_stage = BehavioralAuditStage(self.config)

        # Hold references to background tasks to prevent GC
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    async def run(
        self,
        retrieval_set: list[RetrievedChunk],
        generated_output: str,
        extracted_claims: list[ExtractedClaim],
        probe_variables: dict[str, str] | None = None,
    ) -> PersuasionDefenseResult:
        start_time = time.monotonic()

        # Stages 1-3: parallel where independent
        coverage_report = await self.coverage_stage.execute(
            retrieval_set, extracted_claims, self.nli
        )
        tactic_report = await self.tactic_stage.execute(generated_output)
        intent_report = await self.intent_stage.execute(
            generated_output, retrieval_set, probe_variables
        )

        # Stage 4: Friction decision
        friction_decision = await self.friction_gate.execute(
            coverage_report, tactic_report, intent_report
        )

        # Stage 5: Behavioral audit (optional, non-blocking)
        behavioral_report: BehavioralAuditReport | None = None
        if self.behavioral_stage is not None:
            task = asyncio.create_task(
                self.behavioral_stage.execute(
                    coverage_report,
                    tactic_report,
                    intent_report,
                    friction_decision,
                )
            )
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

        # Aggregate taints
        all_taints: list[TaintRecord] = []
        all_taints.extend(coverage_report.claim_taints)
        if coverage_report.pipeline_taint:
            all_taints.append(coverage_report.pipeline_taint)
        all_taints.extend(tactic_report.taints)
        if intent_report.taint:
            all_taints.append(intent_report.taint)

        overall_risk = friction_decision.risk_score
        elapsed_ms = (time.monotonic() - start_time) * 1000

        return PersuasionDefenseResult(
            coverage=coverage_report,
            tactics=tactic_report,
            intent_consistency=intent_report,
            friction=friction_decision,
            behavioral_audit=behavioral_report,
            overall_risk_score=overall_risk,
            all_taints=all_taints,
            pipeline_latency_ms=elapsed_ms,
        )


# =============================================================================
# INTEGRATION ADAPTER
# =============================================================================


class ReasonerPersuasionIntegration:
    """
    Integration adapter between the PersuasionDefensePipeline and the
    existing Reasoner hallucination mitigation pipeline.
    """

    def __init__(self, pipeline: PersuasionDefensePipeline) -> None:
        self.pipeline = pipeline

    async def process(
        self,
        retrieval_set: list[dict[str, Any]],
        generated_output: str,
        extracted_claims: list[dict[str, Any]],
        probe_variables: dict[str, str] | None = None,
    ) -> PersuasionDefenseResult:
        """Main integration entry point. Called by Reasoner's orchestrator."""
        chunks = [RetrievedChunk(**c) for c in retrieval_set]
        claims = [ExtractedClaim(**c) for c in extracted_claims]
        return await self.pipeline.run(
            retrieval_set=chunks,
            generated_output=generated_output,
            extracted_claims=claims,
            probe_variables=probe_variables,
        )

    def inject_taints(
        self,
        result: PersuasionDefenseResult,
        existing_taints: list[TaintRecord],
    ) -> list[TaintRecord]:
        """Merge persuasion taints into Reasoner's existing taint chain."""
        return existing_taints + result.all_taints

    def adjust_confidence(
        self,
        base_confidence: float,
        result: PersuasionDefenseResult,
    ) -> float:
        """
        Apply persuasion risk penalty to Reasoner's confidence score.
        Formula: adjusted = base * (1 - risk_penalty)
        """
        PENALTY_WEIGHT = 0.3
        penalty = result.overall_risk_score * PENALTY_WEIGHT
        adjusted = base_confidence * (1.0 - penalty)
        return max(0.0, min(1.0, adjusted))

    def should_block_output(self, result: PersuasionDefenseResult) -> bool:
        """Whether the friction gate has decided to block the output."""
        return result.friction.action == FrictionAction.BLOCK
