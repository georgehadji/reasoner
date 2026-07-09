"""Reasoning benchmark: logic puzzles and multi-step inference."""

from __future__ import annotations

import asyncio
from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite


_REASONING_PROMPTS = [
    "If all A are B, and some B are C, can we conclude that some A are C? Explain step by step.",
    "Alice is twice as old as Bob was when Alice was as old as Bob is now. If Alice is 40, how old is Bob?",
    "You have a 3-gallon jug and a 5-gallon jug. How can you measure exactly 4 gallons?",
    "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?",
    "If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets?",
]


class ReasoningSuite(BenchmarkSuite):
    """Evaluate multi-step logical reasoning capability."""

    @property
    def suite_name(self) -> str:
        return "reasoning"

    @property
    def dimension(self) -> str:
        return "reasoning"

    async def run(
        self,
        judge_provider,
        calls_per_suite: int = 10,
    ) -> BenchmarkResult:
        correct = 0
        total = min(calls_per_suite, len(_REASONING_PROMPTS))
        for i in range(total):
            prompt = _REASONING_PROMPTS[i]
            try:
                response = await judge_provider.complete(
                    system_prompt="You are solving a reasoning puzzle. Be precise and step-by-step.",
                    user_prompt=prompt,
                    max_tokens=500,
                    temperature=0.0,
                )
                # Simple heuristic: longer responses = more reasoning effort
                if response and len(response) > 100:
                    correct += 1
            except Exception:
                pass
        score = correct / total if total > 0 else 0.0
        return BenchmarkResult(
            suite_name=self.suite_name,
            dimension=self.dimension,
            score=score,
            sample_count=total,
        )
