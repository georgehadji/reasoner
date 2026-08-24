"""Unit tests for ACR Phase 6: Online Learning Engine.

Tests Thompson Sampling, quality signal aggregation, exploration policy,
and the online learner loop.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reasoner.domain.telemetry import LLMCallTelemetry
from reasoner.infrastructure.learning.exploration import (
    ExplorationPolicy,
)
from reasoner.infrastructure.learning.online_learner import (
    OnlineLearner,
)
from reasoner.infrastructure.learning.quality_signals import (
    QualitySignalAggregator,
)
from reasoner.infrastructure.learning.thompson_sampler import (
    BetaPosterior,
    ThompsonSampler,
)

# ── Beta Posterior ──────────────────────────────────────────────────────

class TestBetaPosterior:
    """Beta posterior distribution behavior."""

    def test_default_prior(self):
        """Default posterior is Beta(1, 1) = uniform."""
        p = BetaPosterior()
        assert p.alpha == 1.0
        assert p.beta == 1.0
        assert p.call_count == 0
        assert p.mean == 0.5  # Uniform prior mean

    def test_update_success(self):
        """Updating with reward=1.0 increases alpha."""
        p = BetaPosterior()
        p.update(1.0)
        assert p.alpha == 2.0  # 1.0 + 1.0
        assert p.beta == 1.0   # 1.0 + (1.0 - 1.0)
        assert p.call_count == 1
        assert p.mean == 2.0 / 3.0  # 2/(2+1)

    def test_update_failure(self):
        """Updating with reward=0.0 increases beta."""
        p = BetaPosterior()
        p.update(0.0)
        assert p.alpha == 1.0  # 1.0 + 0.0
        assert p.beta == 2.0   # 1.0 + 1.0
        assert p.mean == 1.0 / 3.0

    def test_update_partial(self):
        """Partial rewards work correctly."""
        p = BetaPosterior()
        p.update(0.7)
        assert p.alpha == 1.7
        assert p.beta == 1.3  # 1.0 + (1.0 - 0.7)
        assert p.call_count == 1
        assert p.sum_rewards == 0.7

    def test_mean_converges(self):
        """After many updates with same reward, mean converges."""
        p = BetaPosterior()
        for _ in range(100):
            p.update(0.8)
        assert p.mean == pytest.approx(0.8, abs=0.05)
        assert p.std < 0.05  # Low uncertainty after many samples

    def test_std_decreases_with_samples(self):
        """Standard deviation decreases as more data arrives."""
        p = BetaPosterior()
        # Cold start: high uncertainty
        initial_std = p.std
        for _ in range(100):
            p.update(0.5)
        assert p.std < initial_std  # Uncertainty decreased

    def test_sample_bounds(self):
        """Samples from Beta distribution are in [0, 1]."""
        p = BetaPosterior()
        for _ in range(20):
            p.update(0.7 + (0.1 * (_ % 3 - 1)))  # Mixed rewards

        for _ in range(100):
            s = p.sample()
            assert 0.0 <= s <= 1.0

    def test_sample_exploration(self):
        """New model (uniform prior) produces varied samples."""
        p = BetaPosterior()
        samples = [p.sample() for _ in range(100)]
        # Should see values across the range
        assert max(samples) - min(samples) > 0.3
        assert sum(samples) / len(samples) == pytest.approx(0.5, abs=0.15)


# ── Thompson Sampler ────────────────────────────────────────────────────

class TestThompsonSampler:
    """Thompson Sampling model selection."""

    @pytest.fixture
    def sampler(self):
        return ThompsonSampler()

    def test_get_posterior_creates_new(self, sampler):
        """Getting posterior for unknown pair creates a fresh one."""
        p = sampler.get_posterior("model-a", "constructive")
        assert p.alpha == 1.0
        assert p.beta == 1.0

    def test_update_and_retrieve(self, sampler):
        """Update then retrieve reflects the update."""
        sampler.update("model-a", "scoring", 0.9)
        p = sampler.get_posterior("model-a", "scoring")
        assert p.alpha == 1.9
        assert p.call_count == 1

    def test_select_model_best(self, sampler):
        """Select_model picks the best model after training."""
        # Train model-a with high reward, model-b with low
        for _ in range(50):
            sampler.update("model-a", "scoring", 0.9)
            sampler.update("model-b", "scoring", 0.1)

        # Run selection multiple times — model-a should win most often
        wins = {"model-a": 0, "model-b": 0}
        for _ in range(100):
            chosen = sampler.select_model(["model-a", "model-b"], "scoring")
            wins[chosen] += 1

        assert wins["model-a"] > wins["model-b"]

    def test_select_model_empty(self, sampler):
        """Selecting from empty list returns None."""
        assert sampler.select_model([], "scoring") is None

    def test_select_model_single(self, sampler):
        """Selecting from single model returns it."""
        assert sampler.select_model(["model-a"], "scoring") == "model-a"

    def test_export_capabilities(self, sampler):
        """Export returns models with sufficient samples."""
        sampler.update("model-a", "scoring", 0.8)
        sampler.update("model-a", "constructive", 0.7)

        # Below min_samples (5) — not exported
        exported = sampler.export_capabilities(min_samples=5)
        assert "model-a" not in exported

        # Above min_samples
        for _ in range(5):
            sampler.update("model-a", "scoring", 0.8)
            sampler.update("model-a", "constructive", 0.7)

        exported = sampler.export_capabilities(min_samples=5)
        assert "model-a" in exported
        assert "scoring" in exported["model-a"]
        assert "constructive" in exported["model-a"]

    def test_get_stats(self, sampler):
        """Stats return correct summary."""
        sampler.update("model-a", "scoring", 0.5)
        sampler.update("model-b", "constructive", 0.6)
        stats = sampler.get_stats()
        assert stats["model_role_pairs"] == 2
        assert stats["total_observations"] == 2
        assert stats["unique_models"] == 2
        assert stats["unique_roles"] == 2


# ── Quality Signal Aggregator ───────────────────────────────────────────

class TestQualitySignalAggregator:
    """Reward signal computation from telemetry."""

    @pytest.fixture
    def aggregator(self):
        return QualitySignalAggregator()

    @pytest.fixture
    def base_event(self):
        return LLMCallTelemetry(
            call_id="test-1",
            run_id="run-1",
            timestamp="2026-07-08T12:00:00Z",
            model_id="claude-sonnet",
            role="constructive",
            preset_id="multi-perspective-budget",
            method="multi-perspective",
            phase=2,
            latency_ms=1000,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            success=True,
            vendor="anthropic",
            bloc="US",
        )

    def test_success_only(self, aggregator, base_event):
        """Event with only success signal uses success weight."""
        reward = aggregator.compute_reward(base_event)
        # Only success signal available (no json_valid, no critique, no stress)
        # weight_sum = 0.3
        # score = 0.3 * 1.0 / 0.3 = 1.0
        assert reward == 1.0

    def test_success_and_json(self, aggregator, base_event):
        """Event with success + json_valid uses both."""
        event = type(base_event)(
            **{**base_event.__dict__, "json_valid": True}
        )
        reward = aggregator.compute_reward(event)
        # weight_sum = 0.3 + 0.15 = 0.45
        # score = (0.3*1.0 + 0.15*1.0) / 0.45 = 1.0
        assert reward == 1.0

    def test_failure_event(self, aggregator, base_event):
        """Failed events produce lower reward."""
        event = type(base_event)(
            **{**base_event.__dict__, "success": False}
        )
        reward = aggregator.compute_reward(event)
        # Only success signal: score = 0.3*0.0 / 0.3 = 0.0
        assert reward == 0.0

    def test_full_signals(self, aggregator, base_event):
        """All signals available produces weighted blend."""
        event = type(base_event)(
            **{
                **base_event.__dict__,
                "json_valid": True,
                "critique_score": 8.0,
                "stress_test_pass": True,
            }
        )
        reward = aggregator.compute_reward(event)
        # weight_sum = 0.3 + 0.15 + 0.35 + 0.20 = 1.0
        # score = 0.3*1.0 + 0.15*1.0 + 0.35*0.8 + 0.20*1.0 = 0.93
        assert reward == pytest.approx(0.93, abs=0.01)

    def test_critique_mid_range(self, aggregator, base_event):
        """Critique score of 5/10 reduces reward."""
        event = type(base_event)(
            **{**base_event.__dict__, "critique_score": 5.0}
        )
        reward = aggregator.compute_reward(event)
        # weight_sum = 0.3 + 0.35 = 0.65
        # score = (0.3*1.0 + 0.35*0.5) / 0.65 ≈ 0.73
        assert reward == pytest.approx(0.73, abs=0.01)

    def test_batch_rewards(self, aggregator, base_event):
        """Batch processing returns list of (model, role, reward) tuples."""
        batch = [base_event]
        results = aggregator.compute_batch_rewards(batch)
        assert len(results) == 1
        model_id, role, reward = results[0]
        assert model_id == "claude-sonnet"
        assert role == "constructive"
        assert reward == 1.0


# ── Exploration Policy ──────────────────────────────────────────────────

class TestExplorationPolicy:
    """Exploration budget control."""

    def test_default_tier(self):
        """Default tier is balanced with 10% exploration."""
        policy = ExplorationPolicy()
        assert policy.tier == "balanced"
        assert policy.exploration_rate == 0.10

    def test_budget_tier(self):
        """Budget tier has 15% exploration."""
        policy = ExplorationPolicy(tier="budget")
        assert policy.exploration_rate == 0.15

    def test_premium_tier(self):
        """Premium tier has 5% exploration."""
        policy = ExplorationPolicy(tier="premium")
        assert policy.exploration_rate == 0.05

    def test_custom_rate(self):
        """Custom override works."""
        policy = ExplorationPolicy(exploration_rate=0.20)
        assert policy.exploration_rate == 0.20

    def test_should_explore_rate(self):
        """should_explore respects probability."""
        policy = ExplorationPolicy(exploration_rate=0.50)
        explore_count = sum(1 for _ in range(1000) if policy.should_explore())
        assert 400 <= explore_count <= 600  # Within 10% of expected

    def test_warmup_threshold(self):
        """Cold-start models are not warmed up."""
        policy = ExplorationPolicy(warmup_calls=50)
        assert policy.is_warmed_up(0) is False
        assert policy.is_warmed_up(49) is False
        assert policy.is_warmed_up(50) is True
        assert policy.is_warmed_up(100) is True

    def test_effective_rate_cold(self):
        """Cold models always explore (1.0 rate)."""
        policy = ExplorationPolicy(tier="budget")
        assert policy.get_effective_rate(0) == 1.0
        assert policy.get_effective_rate(10) == 1.0

    def test_effective_rate_warm(self):
        """Warm models use tier rate."""
        policy = ExplorationPolicy(tier="budget", warmup_calls=50)
        rate = policy.get_effective_rate(100)
        assert rate == 0.15  # Budget tier rate

    def test_get_stats(self):
        """Stats reflect configuration."""
        policy = ExplorationPolicy(tier="premium")
        stats = policy.get_stats()
        assert stats["tier"] == "premium"
        assert stats["exploration_rate"] == 0.05


# ── Online Learner ──────────────────────────────────────────────────────

class TestOnlineLearner:
    """Online learner batch processing and export."""

    @pytest.fixture
    def learner(self):
        return OnlineLearner()

    @pytest.fixture
    def event(self):
        return LLMCallTelemetry(
            call_id="test-1",
            run_id="run-1",
            timestamp="2026-07-08T12:00:00Z",
            model_id="claude-sonnet",
            role="constructive",
            preset_id="multi-perspective-budget",
            method="multi-perspective",
            phase=2,
            latency_ms=1000,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            success=True,
            vendor="anthropic",
            bloc="US",
        )

    @pytest.mark.asyncio
    async def test_process_batch(self, learner, event):
        """Processing a batch updates sampler posteriors."""
        processed = await learner.process_batch([event])
        assert processed == 1

        posterior = learner.sampler.get_posterior(
            "claude-sonnet", "constructive"
        )
        assert posterior.call_count == 1
        assert posterior.mean > 0.5

    @pytest.mark.asyncio
    async def test_process_multiple_events(self, learner, event):
        """Multiple events are processed correctly."""
        processed = await learner.process_batch([event, event, event])
        assert processed == 3

        posterior = learner.sampler.get_posterior(
            "claude-sonnet", "constructive"
        )
        assert posterior.call_count == 3

    @pytest.mark.asyncio
    async def test_export_to_registry(self, learner, event):
        """Export updates the registry with capability profiles."""
        mock_registry = MagicMock()
        learner.registry = mock_registry

        # Add enough samples for export
        for _ in range(10):
            await learner.process_batch([event])

        exported = await learner.export_to_registry()
        assert exported >= 1

        # Registry was called
        assert mock_registry.update_capabilities.called

    @pytest.mark.asyncio
    async def test_get_stats(self, learner, event):
        """Stats return learner state."""
        await learner.process_batch([event])
        stats = learner.get_stats()
        assert stats["total_observations"] == 1
        assert stats["running"] is False

    def test_stop(self, learner):
        """Stop signals the loop to end."""
        assert learner._running is False
        # run_loop sets _running, stop clears it
        learner._running = True
        learner.stop()
        assert learner._running is False
