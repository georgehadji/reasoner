"""Tests for PipelineField descriptor — get/set/init across all target sub-objects."""

from __future__ import annotations

import pytest


class TestPipelineFieldDescriptor:
    """Verify that PipelineField correctly delegates to sub-objects on PipelineState."""

    def test_core_properties_get_set(self):
        """Core fields: problem, language, candidates, errors."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test problem", preset_name="test")
        assert s.problem == "test problem"

        s.problem = "updated problem"
        assert s.problem == "updated problem"
        assert s.core.problem == "updated problem"

        s.language = "fr"
        assert s.language == "fr"

        s.candidates = []
        assert s.candidates == []
        assert s.core.candidates == []

    def test_meta_properties_get_set(self):
        """Meta fields: phase_tokens, preset_name, quality_hints."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test", preset_name="test")
        s.phase_tokens = {"p1": {"in": 10, "out": 20}}
        assert s.phase_tokens == {"p1": {"in": 10, "out": 20}}
        assert s.meta.phase_tokens == {"p1": {"in": 10, "out": 20}}

        s.preset_name = "coding-budget"
        assert s.preset_name == "coding-budget"

    def test_remainder_properties_get_set(self):
        """Remainder fields: neuro_context, pending_events, web_discovery_results."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test", preset_name="test")
        s.neuro_context = [{"content": "memory", "relevance": 0.9}]
        assert s.neuro_context == [{"content": "memory", "relevance": 0.9}]
        assert s.remainder.neuro_context == [{"content": "memory", "relevance": 0.9}]

        s.pending_events = [{"type": "test"}]
        s.pending_events.append({"type": "test2"})
        assert len(s.pending_events) == 2

    def test_cost_state_properties_get_set(self):
        """Cost fields: total_cost_usd, phase_costs."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test", preset_name="test")
        assert s.total_cost_usd == 0.0  # default

        s.total_cost_usd = 5.50
        assert s.total_cost_usd == 5.50
        assert s.cost_state.total_cost_usd == 5.50

    def test_conversation_state_properties_get_set(self):
        """Conversation fields: conversation_id, turn_number, agent_model."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test", preset_name="test")

        s.conversation_id = "conv-1"
        assert s.conversation_id == "conv-1"
        assert s.conversation_state.conversation_id == "conv-1"

        s.turn_number = 3
        assert s.turn_number == 3

    def test_pipeline_field_repr_on_class(self):
        """Accessing PipelineField from the class (not instance) returns the descriptor."""
        from reasoner.domain.pipeline_state import PipelineField, PipelineState

        field = PipelineState.__dict__.get("problem")
        assert isinstance(field, PipelineField)

    def test_default_values_via_init(self):
        """Constructor defaults should work correctly through descriptors."""
        from reasoner.domain.pipeline_state import PipelineState

        s = PipelineState(problem="test", preset_name="test")
        assert s.language == "English"  # PipelineCore default
        assert s.complexity is None  # default
        assert s.candidates == []  # default
        assert s.scores == []  # default
        assert s.total_cost_usd == 0.0  # default
