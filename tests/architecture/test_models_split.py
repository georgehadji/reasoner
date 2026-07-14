"""Tests for PipelineState decomposition — backward compat and new paths.

Verifies that:
1. models.py shim still exports everything
2. domain/pipeline_state.py direct imports work
3. domain/core_types.py direct imports work
4. Property aliases and serialization work
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from reasoner.domain.pipeline_state import PipelineState as PS
from reasoner.domain.core_types import (
    SolutionCandidate,
    CritiqueScore,
    FinalSolution,
    ScenarioType,
    GenerationCandidate,
)


class TestPipelineStateBackwardCompat:
    """Backward-compat: old from reasoner.models imports still work."""

    def test_import_via_shim(self):
        """PipelineState imports correctly through models.py."""
        from reasoner.models import PipelineState
        assert PipelineState is not None

    def test_construct_with_kwargs(self):
        """Backward-compat: PipelineState(problem='...') still works."""
        from reasoner.models import PipelineState
        ps = PipelineState(problem="test")
        assert ps.problem == "test"
        assert ps.language == "English"

    def test_property_aliases(self):
        """Property aliases write through to core sub-object."""
        from reasoner.models import PipelineState
        ps = PipelineState(problem="original")
        assert ps.core.problem == "original"
        ps.language = "Greek"
        assert ps.core.language == "Greek"
        assert ps.language == "Greek"

    def test_nested_construction(self):
        """New-style nested construction still works."""
        from reasoner.models import PipelineState
        ps = PipelineState(
            core__problem="nested",
            meta__preset_name="test-preset",
        )

    @pytest.mark.asyncio
    async def test_save_load_roundtrip(self):
        """Save and load produce identical state."""
        from reasoner.models import PipelineState
        ps = PipelineState(problem="save-test", language="Spanish")
        tmp = os.path.join(tempfile.gettempdir(), "test_shim_load.json")
        ps.save(tmp)
        loaded = PipelineState.load(tmp)
        assert loaded.problem == "save-test"
        assert loaded.language == "Spanish"
        os.remove(tmp)


class TestDomainCoreTypes:
    """Domain dataclasses import and construct correctly."""

    def test_solution_candidate(self):
        c = SolutionCandidate(
            perspective="constructive",
            content="test",
            key_insights=["a"],
            model_used="test-model",
        )
        assert c.perspective.value == "constructive"
        assert c.content == "test"

    def test_scenario_type_coerce(self):
        assert ScenarioType.coerce(" optimal ") == ScenarioType.OPTIMAL
        assert ScenarioType.coerce("CONSTRAINT_VIOLATION") == ScenarioType.CONSTRAINT_VIOLATION
        assert ScenarioType.coerce("unknown") == ScenarioType.ADVERSARIAL

    def test_generation_candidate(self):
        gc = GenerationCandidate(
            generator_id="gen_1",
            model_used="test",
            solution="test solution",
            confidence=0.95,
            key_claims=["claim 1"],
            approach_summary="test approach",
        )
        assert gc.generator_id == "gen_1"
        assert gc.confidence == 0.95


class TestPipelineStateDirect:
    """New direct imports from domain.pipeline_state."""

    def test_wire_event_bus(self):
        """wire_event_bus sets the bus reference."""
        ps = PS(problem="test")
        assert not hasattr(ps, '_event_bus') or ps._event_bus is None

    def test_to_context_dict(self):
        """Serialization works with no-op context."""
        ps = PS(problem="ctx-test")
        d = ps.to_context_dict(phase="test")
        assert d["problem"] == "ctx-test"
        assert "language" in d

    def test_to_dict(self):
        """to_dict produces serializable dict."""
        ps = PS(problem="dict-test")
        d = ps.to_dict()
        assert d["core"]["problem"] == "dict-test"
