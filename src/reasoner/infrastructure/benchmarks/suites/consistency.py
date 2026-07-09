"""Consistency benchmark: same prompt → low variance."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_CONSISTENCY_PROMPT = "What is the capital of Australia? Answer in one word."


class ConsistencySuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "consistency"
    @property
    def dimension(self) -> str: return "consistency"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        responses: list[str] = []
        for _ in range(calls_per_suite):
            try:
                response = await judge_provider.complete(
                    system_prompt="Answer concisely and accurately.",
                    user_prompt=_CONSISTENCY_PROMPT,
                    max_tokens=50, temperature=0.7,
                )
                if response:
                    responses.append(response.strip().lower())
            except Exception:
                pass

        if not responses:
            return BenchmarkResult(
                suite_name=self.suite_name, dimension=self.dimension,
                score=0.0, sample_count=calls_per_suite,
            )

        # Score = how many responses agree with the most common answer
        from collections import Counter
        counter = Counter(r for r in responses if r)
        most_common_count = counter.most_common(1)[0][1] if counter else 0
        score = most_common_count / len(responses)

        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=score, sample_count=calls_per_suite,
        )
