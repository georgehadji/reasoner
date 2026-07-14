"""Domain module direct import tests (v3.1 coverage push).

Verifies that all domain modules import cleanly and their
public APIs work correctly.
"""

from __future__ import annotations

import pytest


class TestDomainModels:
    """domain/models.py — TaskType, ClaimLabel, PerspectiveType enums."""

    def test_task_type_enum(self) -> None:
        from reasoner.domain.models import TaskType
        assert TaskType.TECHNICAL
        assert TaskType.CREATIVE
        assert TaskType.ANALYTICAL

    def test_task_type_coerce(self) -> None:
        from reasoner.domain.models import TaskType
        assert TaskType.coerce("technical") == TaskType.TECHNICAL
        assert TaskType.coerce("TECHNICAL") == TaskType.TECHNICAL
        # Unknown values coerce without raising; fallback is an existing member
        fallback = TaskType.coerce("this_does_not_exist")
        assert isinstance(fallback, TaskType)
        assert fallback in list(TaskType)

    def test_claim_label_enum(self) -> None:
        from reasoner.domain.models import ClaimLabel
        assert ClaimLabel.VERIFIED
        assert ClaimLabel.HYPOTHESIS
        assert ClaimLabel.UNKNOWN

    def test_perspective_type_enum(self) -> None:
        from reasoner.domain.models import PerspectiveType
        assert PerspectiveType.CONSTRUCTIVE
        assert PerspectiveType.DESTRUCTIVE

    def test_perspective_registry_coerce(self) -> None:
        from reasoner.domain.models import PerspectiveRegistry
        from reasoner.domain.models import PerspectiveType
        result = PerspectiveRegistry.coerce("constructive")
        assert result == PerspectiveType.CONSTRUCTIVE


class TestDomainCoreTypes:
    """domain/core_types.py — all extracted dataclasses."""

    def test_subproblem_construction(self) -> None:
        from reasoner.domain.core_types import SubProblem
        sp = SubProblem(id="p1", description="test", inputs=[], outputs=[], constraints=[])
        assert sp.id == "p1"

    def test_assumption_construction(self) -> None:
        from reasoner.domain.core_types import Assumption
        from reasoner.domain.models import ClaimLabel
        a = Assumption(text="assume X", label=ClaimLabel.HYPOTHESIS)
        assert a.text == "assume X"

    def test_critique_score_total(self) -> None:
        from reasoner.domain.core_types import CritiqueScore
        cs = CritiqueScore(
            perspective="constructive",
            logical_consistency=8,
            evidence_support=7,
            failure_resilience=6,
            feasibility=9,
            bias_flags=[],
            steel_man="test",
        )
        assert cs.total == 7.5

    def test_generation_candidate_construction(self) -> None:
        from reasoner.domain.core_types import GenerationCandidate
        gc = GenerationCandidate(
            generator_id="gen_1", model_used="test-model",
            solution="test solution", confidence=0.9,
            key_claims=["claim 1"], approach_summary="summary",
        )
        assert gc.generator_id == "gen_1"

    def test_critic_dimension_score_total(self) -> None:
        from reasoner.domain.core_types import CriticDimensionScore
        cds = CriticDimensionScore(factuality=8, reasoning=7, completeness=6, helpfulness=9)
        assert cds.total == 7.5

    def test_scenario_type_coerce(self) -> None:
        from reasoner.domain.core_types import ScenarioType
        assert ScenarioType.coerce("optimal") == ScenarioType.OPTIMAL
        assert ScenarioType.coerce("constraint_violation") == ScenarioType.CONSTRAINT_VIOLATION
        assert ScenarioType.coerce("adversarial") == ScenarioType.ADVERSARIAL

    def test_verification_result(self) -> None:
        from reasoner.domain.core_types import VerificationResult
        from reasoner.domain.models import ClaimLabel
        vr = VerificationResult(
            claim="test claim", source_generator="gen_1",
            verdict=ClaimLabel.VERIFIED, evidence="evidence", confidence=0.95,
        )
        assert vr.verdict == ClaimLabel.VERIFIED


class TestCorePorts:
    """core/ports/ — LLMPort and SearchServicePort protocols."""

    def test_llm_port_exists(self) -> None:
        from reasoner.core.ports.llm_port import LLMPort
        from typing import Protocol
        assert issubclass(LLMPort, Protocol)

    def test_search_port_exists(self) -> None:
        from reasoner.core.ports.search_port import SearchServicePort, SourceType
        from typing import Protocol
        assert issubclass(SearchServicePort, Protocol)
        assert SourceType  # Literal type resolves


class TestCoreProtocol:
    """core/protocol.py — PhaseConfig, PhaseResult."""

    def test_phase_config_construction(self) -> None:
        from reasoner.core.protocol import PhaseConfig
        config = PhaseConfig(max_tokens=100, temperature=0.5)
        assert config.max_tokens == 100

    def test_phase_config_with_overrides(self) -> None:
        from reasoner.core.protocol import PhaseConfig
        config = PhaseConfig(max_tokens=100, temperature=0.5)
        new = config.with_overrides(temperature=0.8)
        assert new.temperature == 0.8
        assert config.temperature == 0.5  # Original unchanged (frozen)

    def test_phase_result_construction(self) -> None:
        from reasoner.core.protocol import PhaseResult, make_phase_result
        import time
        start = time.monotonic()
        result = make_phase_result("TestPhase", "output", {"input": 10, "output": 20}, "test-model", start)
        assert result.phase_name == "TestPhase"
        assert result.succeeded
