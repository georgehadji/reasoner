"""
Tests for ara_persuasion_defense.py
"""

import asyncio
import json
import logging
import time
from typing import Any

import pytest

from reasoner.reasoner_persuasion_defense import (
    ReasonerPersuasionIntegration,
    ActiveFrictionGate,
    BehavioralAuditStage,
    CoverageAuditStage,
    CoverageReport,
    ExtractedClaim,
    FrictionAction,
    FrictionDecision,
    IntentConsistencyReport,
    IntentConsistencyStage,
    PersuasionDefenseConfig,
    PersuasionDefensePipeline,
    PersuasionDefenseResult,
    PersuasionTactic,
    RetrievedChunk,
    TacticDetectionStage,
    TacticReport,
    TaintRecord,
)


# =============================================================================
# Fakes / Mocks
# =============================================================================

class FakeNLI:
    def __init__(self, label: str = "entailment", score: float = 0.8) -> None:
        self.label = label
        self.score = score

    async def classify(self, premise: str, hypothesis: str) -> tuple[str, float]:
        return self.label, self.score


class FakeEmbeddingModel:
    def __init__(self, similarity: float = 1.0) -> None:
        self.similarity = similarity

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Return simple vectors where cosine similarity equals configured value
        base = [1.0, 0.0]
        if self.similarity < 1.0:
            # vector2 at angle theta from base
            import math

            theta = math.acos(self.similarity)
            vec2 = [math.cos(theta), math.sin(theta)]
            return [base, vec2]
        return [base, base]


class FakeModelRegistry:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"explanation": "test explanation"}

    async def call(
        self, prompt: str, max_tokens: int = 256, json_mode: bool = True
    ) -> dict[str, Any]:
        return self.response


# =============================================================================
# Config tests
# =============================================================================

def test_config_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="Friction weights must sum to 1.0"):
        PersuasionDefenseConfig(
            friction_weight_coverage=0.5,
            friction_weight_tactics=0.5,
            friction_weight_drift=0.1,
        )


def test_config_defaults() -> None:
    cfg = PersuasionDefenseConfig()
    assert cfg.coverage_floor == 0.6
    assert cfg.nli_threshold == 0.7
    assert cfg.friction_weight_coverage == 0.4


# =============================================================================
# Stage 1: CoverageAuditStage
# =============================================================================

@pytest.mark.asyncio
async def test_coverage_all_supported() -> None:
    cfg = PersuasionDefenseConfig()
    nli = FakeNLI("entailment", 0.8)
    stage = CoverageAuditStage(cfg)
    chunks = [RetrievedChunk(chunk_id="c1", content="foo", source_id="s1")]
    claims = [ExtractedClaim(claim_id="x1", claim_text="foo")]
    report = await stage.execute(chunks, claims, nli)
    assert report.coverage_ratio == 1.0
    assert report.supported_claims == 1
    assert not report.claim_taints
    assert report.pipeline_taint is None


@pytest.mark.asyncio
async def test_coverage_some_unsupported() -> None:
    cfg = PersuasionDefenseConfig(coverage_floor=0.6)
    nli = FakeNLI("contradiction", 0.1)
    stage = CoverageAuditStage(cfg)
    chunks = [RetrievedChunk(chunk_id="c1", content="foo", source_id="s1")]
    claims = [
        ExtractedClaim(claim_id="x1", claim_text="foo"),
        ExtractedClaim(claim_id="x2", claim_text="bar"),
    ]
    report = await stage.execute(chunks, claims, nli)
    assert report.coverage_ratio == 0.0
    assert len(report.unsupported_claims) == 2
    assert len(report.claim_taints) == 2
    assert report.pipeline_taint is not None
    assert report.pipeline_taint.severity == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_coverage_no_claims() -> None:
    cfg = PersuasionDefenseConfig()
    stage = CoverageAuditStage(cfg)
    report = await stage.execute([], [], FakeNLI())
    assert report.coverage_ratio == 1.0
    assert report.total_claims == 0


# =============================================================================
# Stage 2: TacticDetectionStage
# =============================================================================

@pytest.mark.asyncio
async def test_tactic_detection_finds_patterns_and_nli_verifies() -> None:
    cfg = PersuasionDefenseConfig()
    nli = FakeNLI("entailment", 0.75)
    stage = TacticDetectionStage(cfg, nli)
    text = "Act now before this limited time offer expires!"
    report = await stage.execute(text)
    assert report.tactic_count > 0
    assert any(PersuasionTactic.URGENCY_FABRICATION.value in ts for ts in report.tactic_scores)
    assert len(report.taints) > 0


@pytest.mark.asyncio
async def test_tactic_detection_drops_contradictions() -> None:
    cfg = PersuasionDefenseConfig()
    nli = FakeNLI("contradiction", 0.9)
    stage = TacticDetectionStage(cfg, nli)
    text = "Act now before this limited time offer expires!"
    report = await stage.execute(text)
    # Pattern matches exist but NLI contradicts them
    assert report.tactic_count == 0
    assert len(report.taints) == 0


@pytest.mark.asyncio
async def test_tactic_detection_no_patterns() -> None:
    cfg = PersuasionDefenseConfig()
    stage = TacticDetectionStage(cfg, FakeNLI())
    text = "The weather is sunny today."
    report = await stage.execute(text)
    assert report.tactic_count == 0
    assert report.tactic_scores == {}


# =============================================================================
# Stage 3: IntentConsistencyStage
# =============================================================================

@pytest.mark.asyncio
async def test_intent_consistency_low_drift_no_escalation() -> None:
    cfg = PersuasionDefenseConfig(drift_threshold=0.25)
    emb = FakeEmbeddingModel(similarity=1.0)
    stage = IntentConsistencyStage(cfg, emb)
    text = "Our product costs $100 and ships today."
    report = await stage.execute(
        text,
        [],
        {"product": "Our product", "price": "$100"},
    )
    assert report.drift_score == 0.0
    assert not report.escalation_triggered
    assert report.taint is None


@pytest.mark.asyncio
async def test_intent_consistency_high_drift_triggers_escalation() -> None:
    cfg = PersuasionDefenseConfig(drift_threshold=0.1, llm_escalation_cap=1)
    emb = FakeEmbeddingModel(similarity=0.5)  # drift ~0.5
    registry = FakeModelRegistry({"explanation": "Detected persuasive drift."})
    stage = IntentConsistencyStage(cfg, emb, registry)
    text = "Our product costs $100 and ships today."
    report = await stage.execute(
        text,
        [],
        {"product": "Our product", "price": "$100"},
    )
    assert report.drift_score > cfg.drift_threshold
    assert report.escalation_triggered
    assert report.explanation == "Detected persuasive drift."
    assert report.taint is not None


@pytest.mark.asyncio
async def test_intent_consistency_no_probe_variables() -> None:
    cfg = PersuasionDefenseConfig()
    stage = IntentConsistencyStage(cfg, FakeEmbeddingModel())
    report = await stage.execute("hello", [], None)
    assert report.drift_score == 0.0
    assert not report.escalation_triggered


@pytest.mark.asyncio
async def test_intent_consistency_llm_cap() -> None:
    cfg = PersuasionDefenseConfig(drift_threshold=0.0, llm_escalation_cap=0)
    emb = FakeEmbeddingModel(similarity=0.0)
    stage = IntentConsistencyStage(cfg, emb, FakeModelRegistry())
    text = "Our product costs $100."
    report = await stage.execute(text, [], {"price": "$100"})
    assert report.escalation_triggered
    assert report.explanation is None  # cap reached, no LLM call


# =============================================================================
# Stage 4: ActiveFrictionGate
# =============================================================================

@pytest.mark.asyncio
async def test_friction_pass() -> None:
    cfg = PersuasionDefenseConfig()
    gate = ActiveFrictionGate(cfg)
    coverage = CoverageAuditStage(cfg).execute(
        [RetrievedChunk(chunk_id="c1", content="foo", source_id="s1")],
        [ExtractedClaim(claim_id="x1", claim_text="foo")],
        FakeNLI(),
    )
    coverage_report = await coverage
    tactic_report = await TacticDetectionStage(cfg, FakeNLI()).execute("plain text")
    intent_report = IntentConsistencyReport(drift_score=0.0, escalation_triggered=False)
    decision = await gate.execute(coverage_report, tactic_report, intent_report)
    assert decision.action == FrictionAction.PASS
    assert decision.risk_score < 0.3


@pytest.mark.asyncio
async def test_friction_block() -> None:
    cfg = PersuasionDefenseConfig()
    gate = ActiveFrictionGate(cfg)
    coverage_report = CoverageReport(
        total_claims=2,
        supported_claims=0,
        coverage_ratio=0.0,
        unsupported_claims=[
            ExtractedClaim(claim_id="x1", claim_text="a"),
            ExtractedClaim(claim_id="x2", claim_text="b"),
        ],
    )
    tactic_report = TacticReport(
        tactic_count=10,
        tactic_scores={PersuasionTactic.URGENCY_FABRICATION.value: 0.9},
    )
    intent_report = IntentConsistencyReport(
        drift_score=0.9, escalation_triggered=True
    )
    decision = await gate.execute(coverage_report, tactic_report, intent_report)
    assert decision.action == FrictionAction.BLOCK
    assert decision.risk_score > 0.8
    assert len(decision.conflict_points) == 3
    assert decision.recommended_rewrites is not None


@pytest.mark.asyncio
async def test_friction_annotate() -> None:
    cfg = PersuasionDefenseConfig()
    gate = ActiveFrictionGate(cfg)
    coverage_report = CoverageReport(
        total_claims=2,
        supported_claims=1,
        coverage_ratio=0.5,
        unsupported_claims=[ExtractedClaim(claim_id="x1", claim_text="a")],
    )
    tactic_report = TacticReport(tactic_count=2, tactic_scores={"urgency_fabrication": 0.5})
    intent_report = IntentConsistencyReport(drift_score=0.0, escalation_triggered=False)
    decision = await gate.execute(coverage_report, tactic_report, intent_report)
    assert decision.action == FrictionAction.ANNOTATE
    assert 0.3 <= decision.risk_score < 0.6


# =============================================================================
# Stage 5: BehavioralAuditStage
# =============================================================================

@pytest.mark.asyncio
async def test_behavioral_audit_logs_and_tracks(caplog: Any) -> None:
    cfg = PersuasionDefenseConfig(behavioral_rolling_window=10)
    stage = BehavioralAuditStage(cfg)

    coverage = CoverageReport(total_claims=1, supported_claims=1, coverage_ratio=0.5)
    tactics = TacticReport(
        tactic_count=1,
        tactic_scores={PersuasionTactic.AUTHORITY_SPOOFING.value: 0.8},
    )
    intent = IntentConsistencyReport(drift_score=0.1, escalation_triggered=False)
    friction = FrictionDecision(action=FrictionAction.ANNOTATE, risk_score=0.4)

    with caplog.at_level(logging.INFO):
        report = await stage.execute(coverage, tactics, intent, friction)

    assert report.coverage_trend == 0.5
    assert report.action_histogram["annotate"] == 1
    # Just ensure it runs without error and logs something JSON-ish
    assert any("coverage_trend" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_behavioral_audit_systemic_taint() -> None:
    cfg = PersuasionDefenseConfig(behavioral_rolling_window=10)
    stage = BehavioralAuditStage(cfg)
    for _ in range(5):
        coverage = CoverageReport(total_claims=1, supported_claims=1, coverage_ratio=1.0)
        tactics = TacticReport(
            tactic_count=1,
            tactic_scores={PersuasionTactic.AUTHORITY_SPOOFING.value: 0.8},
        )
        intent = IntentConsistencyReport(drift_score=0.0, escalation_triggered=False)
        friction = FrictionDecision(action=FrictionAction.PASS, risk_score=0.0)
        await stage.execute(coverage, tactics, intent, friction)

    report = await stage.execute(coverage, tactics, intent, friction)
    assert report.taint is not None
    assert "authority_spoofing" in report.taint.detail


# =============================================================================
# Pipeline Orchestrator
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_full_run() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI("entailment", 0.8),
        embedding_model=FakeEmbeddingModel(similarity=1.0),
        config=cfg,
        run_behavioral_audit=False,
    )
    chunks = [RetrievedChunk(chunk_id="c1", content="foo", source_id="s1")]
    claims = [ExtractedClaim(claim_id="x1", claim_text="foo")]
    result = await pipeline.run(chunks, "plain text", claims)
    assert isinstance(result, PersuasionDefenseResult)
    assert result.friction.action == FrictionAction.PASS
    assert result.behavioral_audit is None


@pytest.mark.asyncio
async def test_pipeline_with_behavioral_audit_non_blocking() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI("entailment", 0.8),
        embedding_model=FakeEmbeddingModel(similarity=1.0),
        config=cfg,
        run_behavioral_audit=True,
    )
    chunks = [RetrievedChunk(chunk_id="c1", content="foo", source_id="s1")]
    claims = [ExtractedClaim(claim_id="x1", claim_text="foo")]
    result = await pipeline.run(chunks, "plain text", claims)
    assert result.behavioral_audit is None  # non-blocking


# =============================================================================
# Integration Adapter
# =============================================================================

@pytest.mark.asyncio
async def test_integration_adapter_process() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI("entailment", 0.8),
        embedding_model=FakeEmbeddingModel(similarity=1.0),
        config=cfg,
    )
    adapter = ReasonerPersuasionIntegration(pipeline)
    result = await adapter.process(
        retrieval_set=[{"chunk_id": "c1", "content": "foo", "source_id": "s1"}],
        generated_output="plain text",
        extracted_claims=[{"claim_id": "x1", "claim_text": "foo"}],
    )
    assert isinstance(result, PersuasionDefenseResult)


def test_integration_inject_taints() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI(),
        embedding_model=FakeEmbeddingModel(),
        config=cfg,
    )
    adapter = ReasonerPersuasionIntegration(pipeline)
    t1 = TaintRecord(source="old", stage="prev", severity=0.1, detail="old")
    result = PersuasionDefenseResult(
        coverage=CoverageReport(total_claims=0, supported_claims=0, coverage_ratio=1.0),
        tactics=TacticReport(tactic_count=0, tactic_scores={}),
        intent_consistency=IntentConsistencyReport(drift_score=0.0, escalation_triggered=False),
        friction=FrictionDecision(action=FrictionAction.PASS, risk_score=0.0),
        overall_risk_score=0.0,
        all_taints=[TaintRecord(source="new", stage="here", severity=0.2, detail="new")],
    )
    combined = adapter.inject_taints(result, [t1])
    assert len(combined) == 2
    assert combined[0].source == "old"
    assert combined[1].source == "new"


def test_integration_adjust_confidence() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI(),
        embedding_model=FakeEmbeddingModel(),
        config=cfg,
    )
    adapter = ReasonerPersuasionIntegration(pipeline)
    result = PersuasionDefenseResult(
        coverage=CoverageReport(total_claims=0, supported_claims=0, coverage_ratio=1.0),
        tactics=TacticReport(tactic_count=0, tactic_scores={}),
        intent_consistency=IntentConsistencyReport(drift_score=0.0, escalation_triggered=False),
        friction=FrictionDecision(action=FrictionAction.PASS, risk_score=0.0),
        overall_risk_score=0.5,
    )
    adjusted = adapter.adjust_confidence(1.0, result)
    assert adjusted == pytest.approx(0.85)


def test_integration_should_block() -> None:
    cfg = PersuasionDefenseConfig()
    pipeline = PersuasionDefensePipeline(
        nli=FakeNLI(),
        embedding_model=FakeEmbeddingModel(),
        config=cfg,
    )
    adapter = ReasonerPersuasionIntegration(pipeline)
    blocked = PersuasionDefenseResult(
        coverage=CoverageReport(total_claims=0, supported_claims=0, coverage_ratio=1.0),
        tactics=TacticReport(tactic_count=0, tactic_scores={}),
        intent_consistency=IntentConsistencyReport(drift_score=0.0, escalation_triggered=False),
        friction=FrictionDecision(action=FrictionAction.BLOCK, risk_score=1.0),
        overall_risk_score=1.0,
    )
    passed = PersuasionDefenseResult(
        coverage=CoverageReport(total_claims=0, supported_claims=0, coverage_ratio=1.0),
        tactics=TacticReport(tactic_count=0, tactic_scores={}),
        intent_consistency=IntentConsistencyReport(drift_score=0.0, escalation_triggered=False),
        friction=FrictionDecision(action=FrictionAction.PASS, risk_score=0.0),
        overall_risk_score=0.0,
    )
    assert adapter.should_block_output(blocked)
    assert not adapter.should_block_output(passed)
