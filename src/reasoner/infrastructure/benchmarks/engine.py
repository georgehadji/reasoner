"""Benchmark engine — orchestrates model capability evaluation (ACR Phase 7).

Runs benchmark suites on models, stores results to the capability registry,
and manages periodic re-evaluation.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.degrade import degraded
from reasoner.infrastructure.benchmarks.runner import BENCHMARK_BUDGET, BenchmarkRunner

logger = logging.getLogger(__name__)


def _get_default_suites() -> list[Any]:
    """Lazy-import and return all benchmark suite instances."""
    from reasoner.infrastructure.benchmarks.suites.coding import CodingSuite
    from reasoner.infrastructure.benchmarks.suites.consistency import ConsistencySuite
    from reasoner.infrastructure.benchmarks.suites.critical_thinking import CriticalThinkingSuite
    from reasoner.infrastructure.benchmarks.suites.json_fidelity import JsonFidelitySuite
    from reasoner.infrastructure.benchmarks.suites.long_context import LongContextSuite
    from reasoner.infrastructure.benchmarks.suites.multilingual import MultilingualSuite
    from reasoner.infrastructure.benchmarks.suites.reasoning import ReasoningSuite
    from reasoner.infrastructure.benchmarks.suites.writing import WritingSuite

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

        # Reset cost accumulator for per-model budget isolation (D01)
        self.runner.reset_cost()

        run = await self.runner.run_all_suites(model_id, suites, provider)

        # Build capability scores from results
        scores: dict[str, float] = {}
        measured_samples = 0
        unmeasured: list[str] = []
        for result in run.suite_results:
            dim = result.get("dimension", result.get("suite_name", "unknown"))
            samples = result.get("sample_count", 0)
            if samples <= 0:
                # runner.run_suite returns score=0.0 with sample_count=0 for a
                # suite that never ran. Filing that 0.0 as a measurement is the
                # defect: UtilityScorer._capability_match weights it exactly
                # like a model that genuinely failed every prompt, so an
                # outage in one suite demotes the model for that dimension
                # until someone re-benchmarks it.
                unmeasured.append(dim)
                continue
            scores[dim] = result.get("score", 0.0)
            measured_samples += samples

        if unmeasured:
            # update_capabilities replaces the whole profile, so simply
            # omitting a dimension would erase last week's real measurement
            # for it. Carry the previous value instead, and say so.
            previous = self.registry.get_profile(model_id) if self.registry else None
            prev_scores = (
                previous.capabilities.scores
                if previous is not None and previous.capabilities is not None
                else {}
            )
            carried = [dim for dim in unmeasured if dim in prev_scores]
            for dim in carried:
                scores[dim] = prev_scores[dim]
            degraded(
                "benchmarks.capability_profile",
                None,
                exc=RuntimeError("benchmark suite produced no samples"),
                detail=(
                    f"{model_id}: unmeasured {sorted(unmeasured)}, "
                    f"carried forward {sorted(carried)}"
                ),
            )

        # Store to registry. `measured_samples`, not `scores`: a run where
        # every suite died would otherwise stamp a fresh measured_at onto
        # numbers that are entirely carried forward.
        if self.registry and measured_samples:
            import time

            from reasoner.domain.model_capabilities import ModelCapabilities
            caps = ModelCapabilities(
                scores=scores,
                source="benchmark",
                measured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                sample_count=measured_samples,
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
            # Which dimensions in `scores` are not from this run. Without it a
            # caller cannot tell a carried-forward number from a fresh one.
            "unmeasured": sorted(unmeasured),
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
