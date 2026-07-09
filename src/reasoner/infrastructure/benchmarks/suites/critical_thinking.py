"""Critical thinking benchmark: argument analysis and fallacy detection."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_CRITICAL_PROMPTS = [
    "Identify the logical fallacy: 'Everyone believes the new policy is effective, so it must be working.'",
    "Analyze this argument: 'If we allow students to redo exams, they'll never study hard the first time.' What assumptions does it make?",
    "Compare and contrast consequentialism and deontological ethics. Which provides a stronger framework for AI safety?",
    "Evaluate the claim: 'Correlation implies causation.' Provide counterexamples.",
    "Identify biases in this statement: 'Our team's project succeeded because of our hard work, but the competitor's success was just luck.'",
]


class CriticalThinkingSuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "critical_thinking"
    @property
    def dimension(self) -> str: return "critical_thinking"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_CRITICAL_PROMPTS))
        good = 0
        for i in range(total):
            try:
                response = await judge_provider.complete(
                    system_prompt="You are an analytical philosopher. Think carefully and provide structured analysis.",
                    user_prompt=_CRITICAL_PROMPTS[i],
                    max_tokens=600, temperature=0.2,
                )
                if response and len(response) >= 100:
                    good += 1
            except Exception:
                pass
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=good / total if total > 0 else 0.0, sample_count=total,
        )
