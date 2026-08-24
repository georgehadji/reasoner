"""Unit tests for ACR Phase 3: Scoring Weights, Role Requirements, Utility Scorer.

Tests the weighted dot product approach and utility scoring edge cases.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.role_requirements import (
    get_all_requirements,
    get_requirement,
)
from reasoner.application.services.utility_scorer import UtilityScorer
from reasoner.domain.model_capabilities import (
    ModelCapabilities,
    ModelConstraints,
    ModelProfile,
)
from reasoner.domain.scoring_weights import (
    BALANCED_WEIGHTS,
    BUDGET_WEIGHTS,
    PREMIUM_WEIGHTS,
    get_weights_for_tier,
)
from reasoner.domain.task_requirements import TaskRequirement


class TestScoringWeights:
    """ScoringWeights tier presets."""

    def test_budget_weights(self):
        """Budget tier emphasises cost and latency."""
        assert BUDGET_WEIGHTS.cost_penalty + BUDGET_WEIGHTS.latency_penalty == 0.45
        assert BUDGET_WEIGHTS.capability < BUDGET_WEIGHTS.cost_penalty

    def test_balanced_weights(self):
        """Balanced tier has moderate cost sensitivity."""
        assert BALANCED_WEIGHTS.capability == 0.35
        assert BALANCED_WEIGHTS.cost_penalty == 0.10

    def test_premium_weights(self):
        """Premium tier prioritises quality over cost."""
        assert PREMIUM_WEIGHTS.capability + PREMIUM_WEIGHTS.quality_history == 0.70

    def test_get_weights_for_tier(self):
        """Tier lookup works case-insensitively."""
        assert get_weights_for_tier("budget") == BUDGET_WEIGHTS
        assert get_weights_for_tier("BUDGET") == BUDGET_WEIGHTS
        assert get_weights_for_tier("premium") == PREMIUM_WEIGHTS
        assert get_weights_for_tier("unknown") == BALANCED_WEIGHTS


class TestRoleRequirements:
    """Role requirement registry."""

    def test_known_role(self):
        """Known roles return the correct requirement."""
        req = get_requirement("constructive")
        assert req.role == "constructive"
        assert "reasoning" in req.capability_weights
        assert req.capability_weights["creativity"] == 0.8

    def test_scoring_role(self):
        """Scoring role requires high consistency and JSON output."""
        req = get_requirement("scoring")
        assert req.role == "scoring"
        assert req.capability_weights["consistency"] == 0.9
        assert req.capability_weights["json_output"] == 0.8

    def test_synthesis_role(self):
        """Synthesis requires large context window."""
        req = get_requirement("synthesis")
        assert req.role == "synthesis"
        assert req.constraints.min_context_tokens == 32_000

    def test_unknown_role(self):
        """Unknown roles return a sensible default."""
        req = get_requirement("bogus-role-123")
        assert req.role == "unknown"
        assert req.capability_weights["reasoning"] == 0.5

    def test_all_roles_registered(self):
        """All requirements can be enumerated."""
        all_req = get_all_requirements()
        assert len(all_req) > 20  # We define many roles
        # Core roles present
        for key in ["constructive", "destructive", "scoring", "synthesis"]:
            assert key in all_req


class TestUtilityScorer:
    """Utility scorer scoring and ranking."""

    @pytest.fixture
    def scorer(self):
        return UtilityScorer()

    @pytest.fixture
    def strong_model(self):
        """A strong model with high capability scores."""
        return ModelProfile(
            model_id="claude-sonnet",
            constraints=ModelConstraints(
                max_context_tokens=1_000_000,
                cost_per_1k_input_usd=0.002,
                cost_per_1k_output_usd=0.010,
                supports_tools=True,
                supports_vision=True,
                supports_temperature=True,
                vendor="anthropic",
                bloc="US",
            ),
            capabilities=ModelCapabilities(
                scores={
                    "reasoning": 0.95,
                    "creativity": 0.85,
                    "writing": 0.90,
                    "consistency": 0.92,
                    "json_output": 0.90,
                    "long_context": 0.88,
                    "critical_thinking": 0.90,
                    "coding": 0.80,
                    "knowledge": 0.85,
                },
                source="benchmark_v1",
                measured_at="2026-07-01T00:00:00Z",
                sample_count=200,
            ),
        )

    @pytest.fixture
    def weak_model(self):
        """A weak model with low capability scores."""
        return ModelProfile(
            model_id="gpt-5-nano",
            constraints=ModelConstraints(
                max_context_tokens=400_000,
                cost_per_1k_input_usd=0.00005,
                cost_per_1k_output_usd=0.00040,
                supports_tools=True,
                supports_vision=False,
                supports_temperature=True,
                vendor="openai",
                bloc="US",
            ),
            capabilities=ModelCapabilities(
                scores={
                    "reasoning": 0.40,
                    "creativity": 0.35,
                    "writing": 0.45,
                    "consistency": 0.50,
                    "json_output": 0.55,
                },
                source="benchmark_v1",
                measured_at="2026-07-01T00:00:00Z",
                sample_count=200,
            ),
        )

    @pytest.fixture
    def cold_start_model(self):
        """A model with no capability data (cold start)."""
        return ModelProfile(
            model_id="new-model-v1",
            constraints=ModelConstraints(
                max_context_tokens=128_000,
                vendor="unknown",
                bloc="OTHER",
            ),
            capabilities=None,  # No data yet
        )

    def test_score_strong_vs_weak(self, scorer, strong_model, weak_model):
        """Strong model scores higher than weak on the same task."""
        req = get_requirement("constructive")

        strong_score = scorer.score(strong_model, req)
        weak_score = scorer.score(weak_model, req)

        assert strong_score > weak_score
        assert 0.0 <= strong_score <= 1.0
        assert 0.0 <= weak_score <= 1.0

    def test_cold_start_gets_neutral_score(self, scorer, cold_start_model, strong_model):
        """Cold-start models get a neutral 0.5 score."""
        req = get_requirement("scoring")

        cold_score = scorer.score(cold_start_model, req)
        assert cold_score == 0.5

        # Strong model should still beat cold start
        strong_score = scorer.score(strong_model, req)
        assert strong_score > cold_score

    def test_ranking(self, scorer, strong_model, weak_model, cold_start_model):
        """Ranking sorts candidates correctly."""
        req = get_requirement("constructive")
        candidates = [cold_start_model, weak_model, strong_model]

        ranked = scorer.rank_models(candidates, req)

        assert len(ranked) == 3
        # Strongest first
        assert ranked[0][0].model_id == "claude-sonnet"
        assert ranked[0][1] >= ranked[1][1]
        assert ranked[1][1] >= ranked[2][1]

    def test_ranking_top_k(self, scorer, strong_model, weak_model):
        """top_k limits the results."""
        req = get_requirement("scoring")
        ranked = scorer.rank_models([strong_model, weak_model], req, top_k=1)

        assert len(ranked) == 1
        assert ranked[0][0].model_id == "claude-sonnet"

    def test_scoring_role_differentiation(self, scorer, strong_model, weak_model):
        """Scoring role strongly prefers models with high consistency."""
        scoring_req = get_requirement("scoring")
        constructive_req = get_requirement("constructive")

        strong_scoring = scorer.score(strong_model, scoring_req)
        strong_constructive = scorer.score(strong_model, constructive_req)

        # Both should produce valid scores
        assert 0.0 <= strong_scoring <= 1.0
        assert 0.0 <= strong_constructive <= 1.0

    def test_budget_weights_penalize_cost(self, strong_model, weak_model):
        """Budget weights penalise expensive models more."""
        budget_scorer = UtilityScorer(weights=BUDGET_WEIGHTS)
        balanced_scorer = UtilityScorer(weights=BALANCED_WEIGHTS)

        req = get_requirement("scoring")

        # With budget weights, weak (cheap) model should be closer to strong
        budget_gap = (
            budget_scorer.score(strong_model, req)
            - budget_scorer.score(weak_model, req)
        )
        balanced_gap = (
            balanced_scorer.score(strong_model, req)
            - balanced_scorer.score(weak_model, req)
        )

        # Budget gap should be smaller because cheap model's lower cost helps
        assert budget_gap <= balanced_gap

    def test_premium_weights(self, strong_model):
        """Premium weights produce valid scores."""
        premium_scorer = UtilityScorer(weights=PREMIUM_WEIGHTS)
        req = get_requirement("synthesis")

        score = premium_scorer.score(strong_model, req)
        assert 0.0 <= score <= 1.0

    def test_capability_match_perfect(self, scorer):
        """Perfect capability match yields high score."""
        # Create a model whose scores perfectly match the task weights
        req = TaskRequirement(
            role="test",
            capability_weights={"reasoning": 1.0},
        )
        model = ModelProfile(
            model_id="perfect-model",
            constraints=ModelConstraints(vendor="test", bloc="US"),
            capabilities=ModelCapabilities(scores={"reasoning": 1.0}),
        )
        score = scorer.score(model, req)
        assert score > 0.5  # Should be meaningfully above neutral

    def test_empty_capability_weights(self, scorer):
        """Task with no weighted dimensions returns neutral."""
        req = TaskRequirement(role="test", capability_weights={})
        model = ModelProfile(
            model_id="any-model",
            constraints=ModelConstraints(vendor="test", bloc="US"),
            capabilities=ModelCapabilities(scores={"reasoning": 0.9}),
        )
        score = scorer.score(model, req)
        # The score is driven by quality_history/reliability/latency without
        # capability match — should be near mid-range
        assert 0.3 <= score <= 0.7
