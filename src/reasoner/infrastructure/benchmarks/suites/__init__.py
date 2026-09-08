"""Benchmark suites for model capability evaluation (ACR Phase 7).

Each suite evaluates a specific capability dimension and returns
normalized scores (0.0–1.0).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from reasoner.core.degrade import degraded


def report_failed_samples(
    suite: BenchmarkSuite,
    failed: int,
    attempted: int,
    exc: BaseException | None,
) -> None:
    """Record that some of a suite's judge calls never completed.

    Every suite divides its passing samples by the number it *attempted*, so a
    call that raised is scored exactly like a call that returned a wrong
    answer. A suite whose provider is down therefore reports 0.0 over its full
    sample count -- a number indistinguishable from a model that got every
    prompt wrong, and one that `engine.benchmark_model` writes straight into
    the capability registry that routing reads.

    Called once per suite run rather than once per sample: the site label is
    the suite name, which is one of eight fixed values.
    """
    if not failed:
        return
    degraded(
        f"benchmarks.{suite.suite_name}",
        None,
        exc=exc or RuntimeError("judge call failed"),
        detail=f"{failed}/{attempted} samples did not complete",
    )


@dataclass(frozen=True)
class BenchmarkResult:
    """Result of running a single benchmark suite on a model."""

    suite_name: str
    dimension: str
    score: float  # 0.0–1.0
    sample_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class BenchmarkSuite(ABC):
    """Abstract base for a benchmark suite.

    Each suite evaluates one capability dimension and produces a
    normalized 0.0–1.0 score.
    """

    @property
    @abstractmethod
    def suite_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> str: ...

    @abstractmethod
    async def run(
        self,
        judge_provider: Any,  # BaseLLMProvider used to judge responses
        calls_per_suite: int = 10,
    ) -> BenchmarkResult: ...
