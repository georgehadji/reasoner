"""Latency benchmark: VS vs baseline per deployment profile."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig, generate_with_vs
from reasoner.vs_config import VSDeploymentProfile, VSFeatureFlags

BENCHMARK_QUERIES = [
    "Explain quantum computing",
    "What is the capital of France",
    "How does photosynthesis work",
    "Describe the water cycle",
    "What causes earthquakes",
]


class _MockLLM:
    async def generate(self, *, system: str = "", user: str = "") -> str:
        await asyncio.sleep(0.1)  # Simulate 100ms LLM latency
        return '{"candidates": [{"text": "Answer A", "probability": 0.6}, {"text": "Answer B", "probability": 0.4}]}'


class _MockNLI:
    async def score_entailment(self, premise: str, hypothesis: str) -> float:
        await asyncio.sleep(0.02)  # Simulate 20ms NLI latency
        return 0.8


async def measure_pipeline(query: str, vs_disabled: bool, profile: VSDeploymentProfile | None = None) -> float:
    flags = VSFeatureFlags.all_disabled() if vs_disabled else VSFeatureFlags()
    config = VSGenerationConfig(
        strategy=GenerationStrategy.BEST_VERIFIABLE,
        profile=profile or VSDeploymentProfile.BALANCED,
    )
    t0 = time.perf_counter()
    await generate_with_vs(query, config, _MockLLM(), _MockNLI(), flags)
    return (time.perf_counter() - t0) * 1000


async def benchmark_vs_latency() -> list[dict]:
    profiles = [
        VSDeploymentProfile.LATENCY_SENSITIVE,
        VSDeploymentProfile.BALANCED,
        VSDeploymentProfile.MAX_ACCURACY,
    ]
    results = []
    for profile in profiles:
        for query in BENCHMARK_QUERIES:
            baseline = await measure_pipeline(query, vs_disabled=True)
            vs_time = await measure_pipeline(query, vs_disabled=False, profile=profile)
            overhead = ((vs_time - baseline) / baseline * 100) if baseline > 0 else 0.0
            results.append({
                "profile": profile,
                "query": query,
                "baseline_ms": round(baseline, 2),
                "vs_ms": round(vs_time, 2),
                "overhead_pct": round(overhead, 1),
            })
    return results


def write_overhead_table(results: list[dict]) -> None:
    out = Path(__file__).parent / "vs_latency_overhead.md"
    lines = [
        "# VS Latency Overhead Benchmark",
        "",
        "| Profile | Query | Baseline (ms) | VS (ms) | Overhead (%) |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['profile']} | {r['query']} | {r['baseline_ms']} | {r['vs_ms']} | {r['overhead_pct']}% |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Overhead table written to {out}")


async def main() -> None:
    results = await benchmark_vs_latency()
    write_overhead_table(results)

    # Validate AC
    lat_sensitive = [r for r in results if r["profile"] == VSDeploymentProfile.LATENCY_SENSITIVE]
    max_overhead = max(r["overhead_pct"] for r in lat_sensitive)
    print(f"\nMax overhead for LATENCY_SENSITIVE: {max_overhead}%")
    assert max_overhead < 50, f"Overhead too high: {max_overhead}%"
    print("AC met: overhead < 50% for LATENCY_SENSITIVE")


if __name__ == "__main__":
    asyncio.run(main())
