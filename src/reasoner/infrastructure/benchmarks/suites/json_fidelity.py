"""JSON fidelity benchmark: structured output compliance."""

from __future__ import annotations

import json

from reasoner.infrastructure.benchmarks.suites import (
    BenchmarkResult,
    BenchmarkSuite,
    report_failed_samples,
)

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
        failed = 0
        last_exc: BaseException | None = None
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
            # JSONDecodeError is an Exception subclass, so the tuple only ever
            # meant `except Exception` -- and this handler also catches the
            # AttributeError from .strip() on a None response, which is a
            # transport failure and not a fidelity result.
            except Exception as exc:
                failed += 1
                last_exc = exc
        report_failed_samples(self, failed, total, last_exc)
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=valid / total if total > 0 else 0.0, sample_count=total,
        )
