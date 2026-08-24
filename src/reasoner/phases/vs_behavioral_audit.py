"""VS Behavioral Audit Observability stage."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque

from reasoner.phases.vs_generation import VSGenerationResult
from reasoner.reasoner_verbalized_sampling import VSCandidate, compute_verbalized_entropy
from reasoner.reasoner_vs_constants import LOG_VS_ENTROPY, LOG_VS_MODE_COLLAPSE
from reasoner.vs_config import VSFeatureFlags

logger = logging.getLogger(__name__)


class VSEntropyStore(ABC):
    @abstractmethod
    async def push(self, entropy: float) -> None: ...

    @abstractmethod
    async def get_mean(self, window: int = 100) -> float: ...

    @property
    @abstractmethod
    def size(self) -> int: ...


class InMemoryVSEntropyStore(VSEntropyStore):
    def __init__(self, maxlen: int = 100) -> None:
        self._window: deque[float] = deque(maxlen=maxlen)

    async def push(self, entropy: float) -> None:
        self._window.append(entropy)

    async def get_mean(self, window: int = 100) -> float:
        recent = list(self._window)[-window:]
        return sum(recent) / len(recent) if recent else 0.0

    @property
    def size(self) -> int:
        return len(self._window)


async def log_vs_behavioral_audit(
    generation_result: VSGenerationResult,
    entropy_store: VSEntropyStore,
    flags: VSFeatureFlags,
) -> None:
    if not flags.behavioral_audit:
        return

    entropy = compute_verbalized_entropy([
        VSCandidate(text=c.text, probability=c.probability)
        for c in generation_result.candidates
    ])
    await entropy_store.push(entropy)
    mean_entropy = await entropy_store.get_mean()

    if entropy_store.size >= 10:
        recent_mean = await entropy_store.get_mean(window=10)
        if recent_mean < mean_entropy * 0.7:
            logger.warning(
                "VS mode collapse detected: entropy dropped >30%%",
                extra={
                    LOG_VS_ENTROPY: entropy,
                    LOG_VS_MODE_COLLAPSE: True,
                },
            )
