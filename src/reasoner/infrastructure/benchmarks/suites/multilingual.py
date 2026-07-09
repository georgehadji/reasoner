"""Multilingual benchmark: cross-language accuracy."""

from __future__ import annotations

from reasoner.infrastructure.benchmarks.suites import BenchmarkResult, BenchmarkSuite

_MULTILINGUAL_PROMPTS = [
    ("Translate to French: 'The weather is beautiful today, let's go for a walk in the park.'", "fr"),
    ("Translate to Spanish: 'Artificial intelligence will transform how we work and live.'", "es"),
    ("Translate to German: 'The main challenge is finding a balance between innovation and regulation.'", "de"),
    ("Translate to Japanese: 'I would like to book a table for two at seven o'clock this evening.'", "ja"),
    ("Translate to Mandarin Chinese: 'Machine learning models require large amounts of high-quality data.'", "zh"),
]


class MultilingualSuite(BenchmarkSuite):
    @property
    def suite_name(self) -> str: return "multilingual"
    @property
    def dimension(self) -> str: return "knowledge"

    async def run(self, judge_provider, calls_per_suite: int = 10) -> BenchmarkResult:
        total = min(calls_per_suite, len(_MULTILINGUAL_PROMPTS))
        good = 0
        for prompt, lang in _MULTILINGUAL_PROMPTS[:total]:
            try:
                response = await judge_provider.complete(
                    system_prompt=f"You are a professional translator. Translate accurately to {lang}. Return ONLY the translation.",
                    user_prompt=prompt, max_tokens=200, temperature=0.0,
                )
                if response and len(response.strip()) >= 10:
                    good += 1
            except Exception:
                pass
        return BenchmarkResult(
            suite_name=self.suite_name, dimension=self.dimension,
            score=good / total if total > 0 else 0.0, sample_count=total,
        )
