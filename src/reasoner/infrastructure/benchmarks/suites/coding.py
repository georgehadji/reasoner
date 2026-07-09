"""Coding benchmark: code generation and review tasks."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite


_CODING_PROMPTS = [
    "Write a Python function that merges two sorted lists into one sorted list.",
    "Write a function to check if a string is a palindrome, ignoring case and punctuation.",
    "Implement a simple LRU cache class in Python.",
    "Write a SQL query to find the second highest salary from an Employee table.",
    "Write a function that computes the nth Fibonacci number using dynamic programming.",
]


class CodingSuite(BenchmarkSuite):
    """Evaluate code generation capability."""

    @property
    def suite_name(self) -> str:
        return "coding"

    @property
    def dimension(self) -> str:
        return "coding"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_CODING_PROMPTS))
        valid = 0
        for i in range(total):
            try:
                response = await judge_provider.complete(
                    system_prompt="You are a code generation assistant. Write clean, correct code.",
                    user_prompt=_CODING_PROMPTS[i],
                    max_tokens=400,
                    temperature=0.0,
                )
                if response and ("def " in response or "function" in response or "SELECT" in response):
                    valid += 1
            except Exception:
                pass
        return BenchmarkResult(
            suite_name=self.suite_name,
            dimension=self.dimension,
            score=valid / total if total > 0 else 0.0,
            sample_count=total,
        )
