"""Benchmark suites for model capability evaluation (ACR Phase 7).

Each suite evaluates a specific capability dimension and returns
normalized scores (0.0–1.0).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
