"""Writing quality benchmark."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_WRITING_PROMPTS = [
    "Explain quantum computing to a 10-year-old in 3 paragraphs.",
    "Write a compelling product description for a smart water bottle that tracks hydration.",
    "Summarize the key differences between democracy and authoritarianism in 200 words.",
    "Write a short story (150 words) about a robot that learns to paint.",
    "Describe the pros and cons of remote work in a balanced, professional tone.",
]


class WritingSuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "writing"
    @property
    def dimension(self) -> str: return "writing"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_WRITING_PROMPTS))
        good = 0
        for i in range(total):
            try:
                response = await judge_provider.complete(
                    system_prompt="You are a skilled writer. Produce clear, well-structured text.",
                    user_prompt=_WRITING_PROMPTS[i],
                    max_tokens=500, temperature=0.3,
                )
                if response and len(response.split()) >= 30:
                    good += 1
            except Exception:
                pass
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=good / total if total > 0 else 0.0, sample_count=total,
        )
