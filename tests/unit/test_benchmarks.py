"""Unit tests for ACR Phase 7: Benchmark Engine.

Tests benchmark suites, runner, and engine.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult
from reasoner.infrastructure.benchmarks.runner import BenchmarkRunner, BenchmarkRun, BENCHMARK_BUDGET
from reasoner.infrastructure.benchmarks.engine import BenchmarkEngine


class MockProvider:
    """Mock LLM provider for benchmark testing."""

    def __init__(self, model: str = "test-model"):
        self.model = model

    async def complete(self, system_prompt: str, user_prompt: str,
                       max_tokens: int = 100, temperature: float = 0.0) -> str:
        return "This is a mock response of sufficient length to pass benchmark checks. " * 10


class MockRegistry:
    """Mock capability registry."""

    def __init__(self):
        self.updated = []

    def update_capabilities(self, model_id, capabilities):
        self.updated.append((model_id, capabilities))


class TestSuites:
    """Basic benchmark suite tests with mock provider."""

    @pytest.fixture
    def provider(self):
        return MockProvider()

    @pytest.mark.asyncio
    async def test_reasoning_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        suite = ReasoningSuite()
        assert suite.suite_name == "reasoning"
        assert suite.dimension == "reasoning"
        result = await suite.run(provider, calls_per_suite=2)
        assert isinstance(result, BenchmarkResult)
        assert 0.0 <= result.score <= 1.0
        assert result.sample_count == 2

    @pytest.mark.asyncio
    async def test_coding_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
        suite = CodingSuite()
        assert suite.suite_name == "coding"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_writing_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.writing import WritingSuite
        suite = WritingSuite()
        assert suite.suite_name == "writing"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_json_fidelity_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.json_fidelity import JsonFidelitySuite
        suite = JsonFidelitySuite()
        assert suite.suite_name == "json_fidelity"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_long_context_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.long_context import LongContextSuite
        suite = LongContextSuite()
        assert suite.suite_name == "long_context"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_multilingual_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.multilingual import MultilingualSuite
        suite = MultilingualSuite()
        assert suite.suite_name == "multilingual"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_consistency_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.consistency import ConsistencySuite
        suite = ConsistencySuite()
        assert suite.suite_name == "consistency"
        result = await suite.run(provider, calls_per_suite=5)
        assert 0.0 <= result.score <= 1.0
        assert result.sample_count == 5

    @pytest.mark.asyncio
    async def test_critical_thinking_suite(self, provider):
        from reasoner.infrastructure.benchmarks.suites.critical_thinking import CriticalThinkingSuite
        suite = CriticalThinkingSuite()
        assert suite.suite_name == "critical_thinking"
        result = await suite.run(provider, calls_per_suite=2)
        assert 0.0 <= result.score <= 1.0


class TestBenchmarkRunner:
    """Benchmark runner with rate limiting and cost tracking."""

    @pytest.fixture
    def runner(self):
        return BenchmarkRunner(max_concurrent=2, delay_between_calls=0.0)

    @pytest.fixture
    def provider(self):
        return MockProvider()

    @pytest.mark.asyncio
    async def test_run_suite(self, runner, provider):
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        result = await runner.run_suite(ReasoningSuite(), provider)
        assert "suite_name" in result
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_run_all_suites(self, runner, provider):
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
        suites = [ReasoningSuite(), CodingSuite()]

        run = await runner.run_all_suites("test-model", suites, provider)
        assert isinstance(run, BenchmarkRun)
        assert run.model_id == "test-model"
        assert len(run.suite_results) == 2
        assert run.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_budget_ceiling_stops(self, runner, provider):
        """Budget ceiling stops further suite runs."""
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
        from reasoner.infrastructure.benchmarks.suites.writing import WritingSuite

        runner.budget["per_model_warmup_usd"] = 0.0  # Zero budget
        suites = [ReasoningSuite(), CodingSuite(), WritingSuite()]
        run = await runner.run_all_suites("test-model", suites, provider)
        # Should stop after first or second suite due to zero budget
        assert len(run.suite_results) <= 2

    def test_reset_cost(self, runner):
        """Reset cost clears the accumulator."""
        runner._total_cost = 5.0
        runner.reset_cost()
        assert runner._total_cost == 0.0


class TestBenchmarkEngine:
    """Benchmark engine orchestration."""

    @pytest.fixture
    def engine(self):
        registry = MockRegistry()
        return BenchmarkEngine(registry=registry)

    @pytest.fixture
    def provider(self):
        return MockProvider()

    @pytest.mark.asyncio
    async def test_benchmark_model(self, engine, provider):
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
        suites = [ReasoningSuite(), CodingSuite()]

        result = await engine.benchmark_model("test-model", provider, suites=suites)
        assert result["model_id"] == "test-model"
        assert result["suites_run"] == 2
        assert "reasoning" in result["scores"]
        assert "coding" in result["scores"]
        assert result["cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_benchmark_model_stores_to_registry(self, engine, provider):
        """Engine stores results to registry."""
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        result = await engine.benchmark_model(
            "test-model", provider,
            suites=[ReasoningSuite()],
        )
        assert len(engine.registry.updated) == 1
        model_id, caps = engine.registry.updated[0]
        assert model_id == "test-model"
        assert caps.source == "benchmark"

    @pytest.mark.asyncio
    async def test_benchmark_multiple(self, engine, provider):
        """Benchmark multiple models."""
        from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
        results = await engine.benchmark_multiple(
            ["model-a", "model-b"],
            provider_factory=lambda m: provider,
        )
        assert len(results) == 2
        assert results[0]["model_id"] == "model-a"
        assert results[1]["model_id"] == "model-b"

    def test_suites_lazy_loaded(self):
        """Test helper to verify default suites load."""
        from reasoner.infrastructure.benchmarks.engine import _get_default_suites
        suites = _get_default_suites()
        assert len(suites) == 8
        names = [s.suite_name for s in suites]
        for expected in ["reasoning", "coding", "writing", "json_fidelity",
                         "long_context", "multilingual", "consistency",
                         "critical_thinking"]:
            assert expected in names
