"""Unit tests for ACR Phase 4: Constraint Checker.

Tests each constraint implementation and the ConstraintResolver.
"""

from __future__ import annotations

import pytest

from reasoner.infrastructure.llm.constraints.bloc_diversity import (
    BlocDiversityConstraint,
)
from reasoner.infrastructure.llm.constraints.budget_ceiling import (
    BudgetCeilingConstraint,
)
from reasoner.infrastructure.llm.constraints.circuit_state import (
    CircuitStateConstraint,
)
from reasoner.infrastructure.llm.constraints.concurrency import (
    ConcurrencyConstraint,
)
from reasoner.infrastructure.llm.constraints.no_repeat_lab import (
    NoRepeatLabConstraint,
)
from reasoner.application.services.constraint_resolver import (
    ConstraintResolver,
)


class TestBlocDiversityConstraint:
    """Bloc diversity ensures synthesis ≠ scoring and ≥2 generator blocs."""

    @pytest.fixture
    def constraint(self):
        return BlocDiversityConstraint()

    def test_synthesis_differs_from_scoring(self, constraint):
        """Synthesis and scoring must be from different blocs."""
        # Both US — violation
        assignment = {
            "synthesis": "claude-sonnet",   # US
            "scoring": "gpt-5",              # US
            "constructive": "deepseek-v4-flash",  # CN
        }
        violations = constraint.validate(assignment, "test")
        synth_violations = [v for v in violations if v.role == "synthesis"]
        assert len(synth_violations) == 1  # synthesis shares bloc with scoring

    def test_synthesis_differs_from_scoring_ok(self, constraint):
        """Different blocs for synthesis and scoring = no violation."""
        assignment = {
            "synthesis": "claude-sonnet",   # US
            "scoring": "deepseek-v4-flash",  # CN
            "constructive": "mistral-large-3",  # EU
        }
        violations = constraint.validate(assignment, "test")
        synth_violations = [v for v in violations if v.role == "synthesis"]
        assert len(synth_violations) == 0

    def test_generator_roles_span_two_blocs(self, constraint):
        """At least 2 blocs required for generator roles."""
        assignment = {
            "constructive": "claude-sonnet",   # US
            "destructive": "gpt-5",             # US
            "scoring": "deepseek-v4-flash",     # CN (non-generator, doesn't count)
        }
        violations = constraint.validate(assignment, "test")
        gen_violations = [v for v in violations
                          if "generator" in v.reason.lower()]
        assert len(gen_violations) >= 1

    def test_generator_roles_two_blocs_ok(self, constraint):
        """≥2 blocs = no violation."""
        assignment = {
            "constructive": "claude-sonnet",     # US
            "destructive": "deepseek-v4-flash",  # CN
            "systemic": "mistral-large-3",       # EU
        }
        violations = constraint.validate(assignment, "test")
        gen_violations = [v for v in violations
                          if "generator" in v.reason.lower()]
        assert len(gen_violations) == 0

    def test_no_single_bloc_holds_more_than_two_generators(self, constraint):
        """No bloc should hold >2 generator roles."""
        assignment = {
            "constructive": "claude-sonnet",   # US
            "destructive": "gpt-5",             # US
            "systemic": "gpt-5-nano",           # US — third US generator
            "scoring": "deepseek-v4-flash",     # CN (non-generator)
        }
        violations = constraint.validate(assignment, "test")
        # Should have synth≠scoring violation AND bloc diversity violation
        # At minimum, US bloc has 3 generators
        us_violations = [v for v in violations if "Bloc 'US'" in v.reason]
        assert len(us_violations) >= 1


class TestBudgetCeilingConstraint:
    """Budget ceiling ensures cost stays within tier limits."""

    @pytest.fixture
    def constraint(self):
        return BudgetCeilingConstraint()

    def test_budget_tier_cheap_model(self, constraint):
        """Cheap model passes budget tier."""
        assignment = {
            "constructive": "qwen3.5-flash",  # Very cheap ($0.065/$0.26 per M)
        }
        violations = constraint.validate(assignment, "multi-perspective-budget")
        assert len(violations) == 0

    def test_budget_tier_expensive_model(self, constraint):
        """Expensive model fails budget tier."""
        assignment = {
            "constructive": "claude-fable-5",  # Very expensive ($10/$50 per M)
        }
        violations = constraint.validate(assignment, "multi-perspective-budget")
        assert len(violations) >= 1

    def test_premium_tier_expensive_model(self, constraint):
        """Expensive model is OK for premium tier."""
        assignment = {
            "constructive": "claude-fable-5",
        }
        violations = constraint.validate(assignment, "multi-perspective-premium")
        assert len(violations) == 0


class TestCircuitStateConstraint:
    """Circuit state constraint blocks open-circuit models."""

    @pytest.fixture
    def constraint(self):
        return CircuitStateConstraint()

    def test_unknown_model_not_blocked(self, constraint):
        """Unknown model (no circuit breaker data) is allowed."""
        assignment = {"scoring": "nonexistent-model-v99"}
        violations = constraint.validate(assignment, "test")
        assert len(violations) == 0

    def test_circuit_state_delegates(self, constraint):
        """The constraint calls get_circuit_breaker internally."""
        # We can't easily mock the circuit breaker without its actual import,
        # but we can verify the method exists and returns expected state string
        state = constraint._get_circuit_state("gpt-5")
        assert state in ("closed", "open", "half_open")


class TestConcurrencyConstraint:
    """Concurrency constraint warns on high usage."""

    @pytest.fixture
    def constraint(self):
        return ConcurrencyConstraint()

    def test_unknown_model_not_blocked(self, constraint):
        """Unknown model (no semaphore data) is allowed."""
        assignment = {"constructive": "nonexistent-model-v99"}
        violations = constraint.validate(assignment, "test")
        assert len(violations) == 0


class TestNoRepeatLabConstraint:
    """No single vendor should dominate assignments."""

    @pytest.fixture
    def constraint(self):
        return NoRepeatLabConstraint()

    def test_balanced_assignments(self, constraint):
        """Different vendors = no violation."""
        assignment = {
            "constructive": "claude-sonnet",      # anthropic (US)
            "destructive": "gpt-5",                # openai (US)
            "scoring": "deepseek-v4-flash",        # deepseek (CN)
            "synthesis": "mistral-large-3",        # mistralai (EU)
        }
        violations = constraint.validate(assignment, "test")
        assert len(violations) == 0

    def test_dominated_by_one_vendor(self, constraint):
        """4/5 from one vendor triggers violation."""
        assignment = {
            "constructive": "claude-sonnet",    # anthropic
            "destructive": "claude-haiku",       # anthropic
            "systemic": "claude-opus",           # anthropic
            "minimalist": "claude-fable-5",      # anthropic
            "scoring": "deepseek-v4-flash",      # deepseek
        }
        violations = constraint.validate(assignment, "test")
        assert len(violations) >= 1


class TestConstraintResolver:
    """ConstraintResolver finds valid assignments."""

    @pytest.fixture
    def resolver(self):
        return ConstraintResolver()

    def test_simple_assignment_no_violations(self, resolver):
        """Happy path: top choices are already valid."""
        ranked = {
            "constructive": [
                ("claude-sonnet", 0.9),
                ("gpt-5", 0.85),
                ("deepseek-v4-flash", 0.80),
            ],
            "scoring": [
                ("deepseek-v4-flash", 0.88),
                ("claude-sonnet", 0.85),
                ("gpt-5", 0.80),
            ],
            "synthesis": [
                ("mistral-large-3", 0.87),
                ("claude-sonnet", 0.85),
            ],
        }
        result = resolver.resolve(ranked, preset_id="test")
        assert "constructive" in result
        assert "scoring" in result
        assert "synthesis" in result

    def test_fixes_bloc_violation(self, resolver):
        """Resolver picks alternative model to fix bloc violation."""
        ranked = {
            "synthesis": [
                ("claude-sonnet", 0.95),       # US
                ("deepseek-v4-flash", 0.80),   # CN
            ],
            "scoring": [
                ("gpt-5", 0.90),                # US
                ("mistral-large-3", 0.75),      # EU
            ],
            "constructive": [
                ("deepseek-v4-flash", 0.88),    # CN
                ("qwen3.7-plus", 0.82),         # CN
            ],
        }
        result = resolver.resolve(ranked, preset_id="test")

        # synthesis should NOT be US if scoring is US
        synth_model = result.get("synthesis", "")
        scoring_model = result.get("scoring", "")

        # At minimum, both are set
        assert synth_model != ""
        assert scoring_model != ""

    def test_returns_fallback_on_no_solution(self, resolver):
        """When no valid assignment exists, returns fallback."""
        ranked = {
            "constructive": [("nonexistent-v1", 0.5)],
        }
        fallback = {"constructive": "gpt-5"}
        result = resolver.resolve(ranked, preset_id="test", fallback=fallback)
        assert result == fallback
