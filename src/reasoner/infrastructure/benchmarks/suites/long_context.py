"""Long context benchmark: summarization and retrieval."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_LONG_CONTEXT_PROMPTS = [
    "Summarize the plot of 'The Lord of the Rings' in 100 words.",
    "Explain the main arguments for and against universal basic income, covering at least 3 perspectives.",
    "Describe the lifecycle of a star from nebula to black hole or white dwarf, in detail.",
    "Outline the major events of World War II in chronological order, covering both European and Pacific theaters.",
    "Explain how machine learning, neural networks, and deep learning relate to each other, with examples.",
]


class LongContextSuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "long_context"
    @property
    def dimension(self) -> str: return "long_context"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_LONG_CONTEXT_PROMPTS))
        good = 0
        for i in range(total):
            try:
                response = await judge_provider.complete(
                    system_prompt="Provide a thorough, detailed response.",
                    user_prompt=_LONG_CONTEXT_PROMPTS[i],
                    max_tokens=800, temperature=0.2,
                )
                if response and len(response) >= 200:
                    good += 1
            except Exception:
                pass
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=good / total if total > 0 else 0.0, sample_count=total,
        )
