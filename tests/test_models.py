"""Tests for models module including state persistence."""

import tempfile
from pathlib import Path

import pytest

from reasoner.models import (
    Assumption,
    ClaimLabel,
    Decomposition,
    PerspectiveType,
    PipelineCore,
    PipelineState,
    ScenarioType,
    SolutionCandidate,
    SubProblem,
    TaskType,
    load,
    save,
)


class TestPipelineStatePersistence:
    """Test state save/load functionality."""

    def test_save_and_load_roundtrip(self):
        """Test that save followed by load preserves state."""
        # Create a state with some data
        state = PipelineState(
            core=PipelineCore(
                problem="Test problem",
                task_type=TaskType.ANALYTICAL,
                task_type_rationale="Test rationale",
                language="English",
            ),
        )

        # Add decomposition
        state.decomposition = Decomposition(
            sub_problems=[
                SubProblem(
                    id="SP1",
                    description="Test sub-problem",
                    inputs=["input1"],
                    outputs=["output1"],
                    constraints=["constraint1"],
                )
            ],
            assumptions=[
                Assumption(
                    text="Test assumption",
                    label=ClaimLabel.HYPOTHESIS,
                    rationale="Test rationale",
                )
            ],
            failure_modes=["Failure mode 1"],
            raw_response="Raw response",
        )

        # Add candidates
        state.candidates = [
            SolutionCandidate(
                perspective=PerspectiveType.CONSTRUCTIVE,
                content="Test content",
                key_insights=["Insight 1"],
                model_used="claude-sonnet",
            )
        ]

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)

            # Load and verify
            loaded = load(temp_path)

            assert loaded.problem == state.problem
            assert loaded.task_type == state.task_type
            assert loaded.task_type_rationale == state.task_type_rationale
            assert loaded.language == state.language

            # Verify decomposition
            assert loaded.decomposition is not None
            assert len(loaded.decomposition.sub_problems) == 1
            assert loaded.decomposition.sub_problems[0].id == "SP1"
            assert loaded.decomposition.assumptions[0].label == ClaimLabel.HYPOTHESIS

            # Verify candidates
            assert len(loaded.candidates) == 1
            assert loaded.candidates[0].perspective == PerspectiveType.CONSTRUCTIVE

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_to_dict_serializes_enums(self):
        """Test that enums are serialized to strings."""
        state = PipelineState(
            core=PipelineCore(
                problem="Test",
                task_type=TaskType.STRATEGIC,
            ),
        )

        data = state.to_dict()
        assert data["core"]["task_type"] == "strategic"
        assert isinstance(data["core"]["task_type"], str)

    def test_load_reconstructs_enums(self):
        """Test that enums are reconstructed from strings."""
        state = PipelineState(
            core=PipelineCore(
                problem="Test",
                task_type=TaskType.CREATIVE,
            ),
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)
            loaded = load(temp_path)

            assert loaded.task_type == TaskType.CREATIVE
            assert isinstance(loaded.task_type, TaskType)

        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestPipelineStateContext:
    """Test context dictionary generation."""

    def test_to_context_dict_structure(self):
        state = PipelineState(core=PipelineCore(problem="Test problem"))

        context = state.to_context_dict()

        assert "problem" in context
        assert "task_type" in context
        assert "sub_problems" in context
        assert "assumptions" in context
        assert "candidates" in context
        assert "scores" in context


class TestScenarioTypeCoercion:
    """Stress-test enums should tolerate common LLM casing variants."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("optimal", ScenarioType.OPTIMAL),
            ("OPTIMAL", ScenarioType.OPTIMAL),
            ("constraint_violation", ScenarioType.CONSTRAINT_VIOLATION),
            ("CONSTRAINT_VIOLATION", ScenarioType.CONSTRAINT_VIOLATION),
            ("constraint-violation", ScenarioType.CONSTRAINT_VIOLATION),
            ("adversarial", ScenarioType.ADVERSARIAL),
            ("ADVERSARIAL", ScenarioType.ADVERSARIAL),
        ],
    )
    def test_coerce_accepts_enum_names_and_variants(self, raw, expected):
        assert ScenarioType.coerce(raw) == expected

    def test_coerce_unknown_fallback_to_adversarial(self):
        """Adversarial discovery: LLMs invent scenario names that must not crash parsing."""
        assert ScenarioType.coerce("supply_chain_collapse") == ScenarioType.ADVERSARIAL
        assert ScenarioType.coerce("cyberattack") == ScenarioType.ADVERSARIAL
        assert ScenarioType.coerce("market crash") == ScenarioType.ADVERSARIAL


class TestStateDeserializationRobustness:
    """BUG-002 regression tests: State deserialization must handle malformed data."""

    def test_load_truncated_sub_problems(self):
        """Test loading state with missing sub_problem fields."""
        # Create a state and save it
        state = PipelineState(core=PipelineCore(problem="Test"))
        state.decomposition = Decomposition(
            sub_problems=[
                SubProblem(id="SP1", description="Test", inputs=[], outputs=[], constraints=[])
            ],
            assumptions=[],
            failure_modes=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)

            # Corrupt the file by removing fields from sub_problems
            import json
            with open(temp_path) as f:
                data = json.load(f)

            # Remove required fields from sub_problem
            data['core']['decomposition']['sub_problems'][0] = {
                'id': 'SP1',
                # Missing: description, inputs, outputs, constraints
            }

            with open(temp_path, 'w') as f:
                json.dump(data, f)

            # Should load without crashing, using defaults for missing fields
            loaded = load(temp_path)
            assert loaded.decomposition is not None
            # Sub_problem should be loaded with default empty values
            assert len(loaded.decomposition.sub_problems) == 1
            assert loaded.decomposition.sub_problems[0].id == 'SP1'
            assert loaded.decomposition.sub_problems[0].description == ''
            assert loaded.decomposition.sub_problems[0].inputs == []
            assert loaded.decomposition.sub_problems[0].outputs == []
            assert loaded.decomposition.sub_problems[0].constraints == []

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_wrong_type_for_list_fields(self):
        """Test loading state where list fields have wrong types."""
        state = PipelineState(core=PipelineCore(problem="Test"))
        state.decomposition = Decomposition(
            sub_problems=[
                SubProblem(id="SP1", description="Test", inputs=["in1"], outputs=["out1"], constraints=["c1"])
            ],
            assumptions=[],
            failure_modes=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)

            # Corrupt: change list fields to strings
            import json
            with open(temp_path) as f:
                data = json.load(f)

            data['core']['decomposition']['sub_problems'][0]['inputs'] = "not_a_list"
            data['core']['decomposition']['sub_problems'][0]['outputs'] = 123
            data['core']['decomposition']['sub_problems'][0]['constraints'] = None

            with open(temp_path, 'w') as f:
                json.dump(data, f)

            # Should load with type coercion
            loaded = load(temp_path)
            assert loaded.decomposition is not None
            assert len(loaded.decomposition.sub_problems) == 1
            # Should be coerced to lists
            assert isinstance(loaded.decomposition.sub_problems[0].inputs, list)
            assert isinstance(loaded.decomposition.sub_problems[0].outputs, list)
            assert isinstance(loaded.decomposition.sub_problems[0].constraints, list)

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_empty_state(self):
        """Test loading minimal/empty state."""
        state = PipelineState(core=PipelineCore(problem="Test"))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)

            # Corrupt: remove decomposition entirely
            import json
            with open(temp_path) as f:
                data = json.load(f)

            del data['core']['decomposition']

            with open(temp_path, 'w') as f:
                json.dump(data, f)

            # Should load with None decomposition
            loaded = load(temp_path)
            assert loaded.decomposition is None

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_malformed_assumption_enum(self):
        """Test loading state with invalid enum value in assumption."""
        state = PipelineState(core=PipelineCore(problem="Test"))
        state.decomposition = Decomposition(
            sub_problems=[],
            assumptions=[
                Assumption(text="Test", label=ClaimLabel.HYPOTHESIS, rationale="Why")
            ],
            failure_modes=[],
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            save(state, temp_path)

            # Corrupt: use invalid enum value
            import json
            with open(temp_path) as f:
                data = json.load(f)

            data['core']['decomposition']['assumptions'][0]['label'] = 'INVALID_LABEL'

            with open(temp_path, 'w') as f:
                json.dump(data, f)

            # Should load with fallback to UNKNOWN
            loaded = load(temp_path)
            assert loaded.decomposition is not None
            # Invalid label should fallback to UNKNOWN or skip entry
            if len(loaded.decomposition.assumptions) > 0:
                assert loaded.decomposition.assumptions[0].label in [ClaimLabel.UNKNOWN, ClaimLabel.HYPOTHESIS]

        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
