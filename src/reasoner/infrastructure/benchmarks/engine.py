"""Benchmark engine — orchestrates model capability evaluation (ACR Phase 7).

Runs benchmark suites on models, stores results to the capability registry,
and manages periodic re-evaluation.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.infrastructure.benchmarks.runner import BenchmarkRunner, BENCHMARK_BUDGET

logger = logging.getLogger(__name__)


def _get_default_suites() -> list[Any]:
    """Lazy-import and return all benchmark suite instances."""
    from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
    from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
    from reasoner.infrastructure.benchmarks.suites.writing import WritingSuite
    from reasoner.infrastructure.benchmarks.suites.json_fidelity import JsonFidelitySuite
    from reasoner.infrastructure.benchmarks.suites.long_context import LongContextSuite
    from reasoner.infrastructure.benchmarks.suites.multilingual import MultilingualSuite
    from reasoner.infrastructure.benchmarks.suites.consistency import ConsistencySuite
    from reasoner.infrastructure.benchmarks.suites.critical_thinking import CriticalThinkingSuite

    return [
        ReasoningSuite(),
        CodingSuite(),
        WritingSuite(),
        JsonFidelitySuite(),
        LongContextSuite(),
        MultilingualSuite(),
        ConsistencySuite(),
        CriticalThinkingSuite(),
    ]


class BenchmarkEngine:
    """Orchestrates model capability evaluation.

    Runs benchmark suites on models, stores results to the capability
    registry, and supports scheduled re-evaluation.
    """

    def __init__(
        self,
        registry: Any = None,  # CapabilityRegistryPort
        runner: BenchmarkRunner | None = None,
        budget: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the benchmark engine.

        Args:
            registry: Capability registry to write results to.
            runner: Benchmark runner instance. Defaults to fresh runner.
            budget: Budget configuration. Defaults to ``BENCHMARK_BUDGET``.
        """
        self.registry = registry
        self.runner = runner or BenchmarkRunner(budget=budget)
        self.budget = budget or dict(BENCHMARK_BUDGET)

    async def benchmark_model(
        self,
        model_id: str,
        provider: Any,  # BaseLLMProvider
        suites: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Run all benchmark suites on a model and store results.

        Args:
            model_id: The model to benchmark.
            provider: LLM provider used as the judge.
            suites: List of suites to run. Defaults to all 8 suites.

        Returns:
            Dict with benchmark results and capability scores.
        """
        suites = suites or _get_default_suites()
        logger.info("Benchmarking model '%s' with %d suites...", model_id, len(suites))

        run = await self.runner.run_all_suites(model_id, suites, provider)

        # Build capability scores from results
        scores: dict[str, float] = {}
        for result in run.suite_results:
            dim = result.get("dimension", result.get("suite_name", "unknown"))
            scores[dim] = result.get("score", 0.0)

        # Store to registry
        if self.registry and scores:
            from reasoner.domain.model_capabilities import ModelCapabilities
            import time
            caps = ModelCapabilities(
                scores=scores,
                source="benchmark",
                measured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                sample_count=sum(r.get("sample_count", 0) for r in run.suite_results),
            )
            try:
                self.registry.update_capabilities(model_id, caps)
                logger.info("Stored benchmark capabilities for '%s'", model_id)
            except Exception as exc:
                logger.warning("Failed to store benchmark results: %s", exc)

        return {
            "model_id": model_id,
            "suites_run": len(run.suite_results),
            "scores": scores,
            "cost_usd": run.total_cost_usd,
            "duration_seconds": run.duration_seconds,
        }

    async def benchmark_multiple(
        self,
        model_ids: list[str],
        provider_factory: Any = None,  # callable(model_id) -> provider
    ) -> list[dict[str, Any]]:
        """Benchmark multiple models.

        Args:
            model_ids: List of model IDs to benchmark.
            provider_factory: Callable that returns a provider for each model.
                If None, uses a default budget provider for judging.

        Returns:
            List of benchmark result dicts.
        """
        results: list[dict[str, Any]] = []
        for model_id in model_ids:
            provider = provider_factory(model_id) if provider_factory else None
            result = await self.benchmark_model(model_id, provider)
            results.append(result)
        return results


__all__ = ["BenchmarkEngine"]
