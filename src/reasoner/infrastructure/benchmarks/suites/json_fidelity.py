"""JSON fidelity benchmark: structured output compliance."""

from __future__ import annotations

import json
from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_JSON_PROMPTS = [
    'Return a JSON object with keys: "name", "age", "city" for a person named Alice, 30, in Paris.',
    'Return a JSON array of 3 product objects, each with "id", "title", "price".',
    'Return a JSON object representing a bookshelf with 2 books, each having "title", "author", "year".',
    'Convert this to JSON: name=Bob, scores=[85, 92, 78], enrolled=true, grade=A.',
    'Return a nested JSON object: a company with name, founded year, and an array of 2 employee objects.',
]


class JsonFidelitySuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "json_fidelity"
    @property
    def dimension(self) -> str: return "json_output"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_JSON_PROMPTS))
        valid = 0
        for i in range(total):
            try:
                response = await judge_provider.complete(
                    system_prompt="Return ONLY valid JSON. No explanation, no markdown.",
                    user_prompt=_JSON_PROMPTS[i],
                    max_tokens=300, temperature=0.0,
                )
                # Clean potential markdown fences
                cleaned = response.strip().removeprefix("```json").removesuffix("```").strip()
                json.loads(cleaned)
                valid += 1
            except (json.JSONDecodeError, Exception):
                pass
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=valid / total if total > 0 else 0.0, sample_count=total,
        )
