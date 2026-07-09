"""Async benchmark runner with rate limiting and cost caps (ACR Phase 7)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default budget configuration
BENCHMARK_BUDGET = {
    "per_model_warmup_usd": 2.00,
    "weekly_reeval_usd": 5.00,
    "calls_per_suite": 10,
    "suites_per_model": 8,
    "use_cheapest_judge": True,
}


@dataclass
class BenchmarkRun:
    """Result of running benchmarks on one model."""

    model_id: str
    suite_results: list[dict[str, Any]] = field(default_factory=list)
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None


class BenchmarkRunner:
    """Async runner that executes benchmark suites with rate limiting and cost caps.

    Ensures benchmarks don't exceed budget and don't overwhelm provider rate limits.
    """

    def __init__(
        self,
        budget: dict[str, Any] | None = None,
        max_concurrent: int = 2,
        delay_between_calls: float = 0.5,
    ) -> None:
        """Initialise the runner.

        Args:
            budget: Budget configuration dict. Defaults to ``BENCHMARK_BUDGET``.
            max_concurrent: Maximum concurrent LLM calls during benchmarking.
            delay_between_calls: Delay in seconds between calls to avoid rate limits.
        """
        self.budget = budget or dict(BENCHMARK_BUDGET)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._delay = delay_between_calls
        self._total_cost: float = 0.0

    async def run_suite(
        self,
        suite: Any,  # BenchmarkSuite instance
        provider: Any,  # BaseLLMProvider used as judge
    ) -> dict[str, Any]:
        """Run a single benchmark suite with rate limiting.

        Returns:
            Dict with ``suite_name``, ``dimension``, ``score``, ``sample_count``.
        """
        async with self._semaphore:
            start = time.perf_counter()
            try:
                result = await suite.run(
                    judge_provider=provider,
                    calls_per_suite=self.budget.get("calls_per_suite", 10),
                )
                elapsed = time.perf_counter() - start
                logger.info(
                    "Benchmark suite '%s' on %s: score=%.3f, samples=%d, %.1fs",
                    suite.suite_name, provider.model if hasattr(provider, "model") else "judge",
                    result.score, result.sample_count, elapsed,
                )
                await asyncio.sleep(self._delay)
                return {
                    "suite_name": result.suite_name,
                    "dimension": result.dimension,
                    "score": result.score,
                    "sample_count": result.sample_count,
                }
            except Exception as exc:
                logger.warning("Benchmark suite '%s' failed: %s", suite.suite_name, exc)
                return {
                    "suite_name": suite.suite_name,
                    "dimension": suite.dimension,
                    "score": 0.0,
                    "sample_count": 0,
                    "error": str(exc),
                }

    async def run_all_suites(
        self,
        model_id: str,
        suites: list[Any],
        provider: Any,
    ) -> BenchmarkRun:
        """Run all benchmark suites on a model.

        Args:
            model_id: The model being benchmarked (for reporting).
            suites: List of BenchmarkSuite instances.
            provider: LLM provider used as the judge.

        Returns:
            ``BenchmarkRun`` with all results.
        """
        start = time.perf_counter()
        suite_results: list[dict[str, Any]] = []

        for suite in suites:
            result = await self.run_suite(suite, provider)
            suite_results.append(result)

            # Estimate cost and check budget
            calls = result.get("sample_count", 0)
            estimated_cost = calls * 0.0005  # ~$0.0005 per judge call
            self._total_cost += estimated_cost

            if self._total_cost > self.budget.get("per_model_warmup_usd", 2.0):
                logger.warning(
                    "Benchmark budget exceeded for %s ($%.2f > $%.2f)",
                    model_id, self._total_cost,
                    self.budget["per_model_warmup_usd"],
                )
                break

        duration = time.perf_counter() - start
        return BenchmarkRun(
            model_id=model_id,
            suite_results=suite_results,
            total_cost_usd=self._total_cost,
            duration_seconds=duration,
        )

    def reset_cost(self) -> None:
        """Reset the accumulated cost counter."""
        self._total_cost = 0.0


__all__ = ["BenchmarkRunner", "BenchmarkRun", "BENCHMARK_BUDGET"]
