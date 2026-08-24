"""VS Generation Stage — Track 5B (CRITICAL PATH)."""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from reasoner.exceptions import ProviderError
from reasoner.reasoner_verbalized_sampling import VSMode, build_vs_prompt, parse_vs_response
from reasoner.reasoner_vs_constants import (
    LOG_VS_CANDIDATE_RANK,
    LOG_VS_K,
    LOG_VS_NLI_SCORES,
    LOG_VS_STRATEGY,
    PROFILE_NLI_BUDGET,
    VS_K_GENERATION,
)
from reasoner.vs_config import VSDeploymentProfile, VSFeatureFlags

logger = logging.getLogger(__name__)


class _LLMClient(Protocol):
    async def generate(self, *, system: str = "", user: str = "") -> str: ...


class _NLIGate(Protocol):
    async def score_entailment(self, premise: str, hypothesis: str) -> float: ...


class GenerationStrategy(str, Enum):
    BEST_VERIFIABLE = "best_verifiable"
    ENSEMBLE = "ensemble"
    TOP_PROBABILITY = "top_probability"


class VSGenerationConfig(BaseModel):
    strategy: GenerationStrategy = GenerationStrategy.BEST_VERIFIABLE
    k: int = VS_K_GENERATION
    max_parallel_nli: int = Field(default=3, le=VS_K_GENERATION)
    profile: VSDeploymentProfile = VSDeploymentProfile.BALANCED


class GenerationCandidate(BaseModel):
    text: str
    probability: float
    nli_score: float | None = None
    selected: bool = False


class VSGenerationResult(BaseModel):
    candidates: list[GenerationCandidate]
    selected: GenerationCandidate
    vs_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidates")
    @classmethod
    def exactly_one_selected(cls, v: list[GenerationCandidate]) -> list[GenerationCandidate]:
        selected = [c for c in v if c.selected]
        if len(selected) != 1:
            raise ValueError(f"Exactly one candidate must be selected, got {len(selected)}")
        return v


async def _generate_with_vs_inner(
    query: str,
    config: VSGenerationConfig,
    llm_client: _LLMClient,
    nli_gate: _NLIGate,
    flags: VSFeatureFlags,
    simplified: bool = False,
) -> VSGenerationResult:
    """Inner generation logic (no fallback wrapping)."""
    if not flags.generation:
        text = await llm_client.generate(user=query)
        cand = GenerationCandidate(text=text, probability=1.0, nli_score=None, selected=True)
        return VSGenerationResult(
            candidates=[cand],
            selected=cand,
            vs_metadata={"strategy": "direct", "k": 1},
        )

    k = config.k
    system, user = build_vs_prompt(query, VSMode.STANDARD, k)
    if simplified:
        user = f"Query: {query}\nGive exactly {k} short answers as JSON."

    raw = await llm_client.generate(system=system, user=user)
    vs_result = parse_vs_response(raw)

    candidates = [
        GenerationCandidate(text=c.text, probability=c.probability, nli_score=None, selected=False)
        for c in vs_result.candidates
    ]

    # Strategy routing
    if config.strategy == GenerationStrategy.TOP_PROBABILITY:
        selected = max(candidates, key=lambda c: c.probability)
        selected.selected = True
        return _build_result(candidates, selected, config)

    if config.strategy == GenerationStrategy.ENSEMBLE:
        selected = max(candidates, key=lambda c: c.probability)
        selected.selected = True
        return _build_result(candidates, selected, config)

    # BEST_VERIFIABLE: pre-commit NLI budget
    nli_budget = PROFILE_NLI_BUDGET[config.profile]
    nli_tasks = [
        asyncio.create_task(nli_gate.score_entailment(query, c.text))
        for c in candidates[:nli_budget]
    ]
    nli_scores = await asyncio.gather(*nli_tasks, return_exceptions=True)

    for i, score in enumerate(nli_scores):
        if isinstance(score, Exception):
            candidates[i].nli_score = None
        else:
            candidates[i].nli_score = score

    scored = [c for c in candidates if c.nli_score is not None]
    if scored:
        selected = max(scored, key=lambda c: c.nli_score or 0.0)
    else:
        selected = candidates[0]
    selected.selected = True

    return _build_result(candidates, selected, config)


def _build_result(
    candidates: list[GenerationCandidate],
    selected: GenerationCandidate,
    config: VSGenerationConfig,
) -> VSGenerationResult:
    vs_metadata = {
        LOG_VS_STRATEGY: config.strategy,
        LOG_VS_K: config.k,
        LOG_VS_NLI_SCORES: [c.nli_score for c in candidates],
        LOG_VS_CANDIDATE_RANK: candidates.index(selected),
    }
    return VSGenerationResult(
        candidates=candidates,
        selected=selected,
        vs_metadata=vs_metadata,
    )


async def generate_with_vs(
    query: str,
    config: VSGenerationConfig,
    llm_client: _LLMClient,
    nli_gate: _NLIGate,
    flags: VSFeatureFlags,
) -> VSGenerationResult:
    """3-level fallback wrapper around _generate_with_vs_inner."""
    try:
        return await _generate_with_vs_inner(query, config, llm_client, nli_gate, flags)
    except ProviderError as e:
        logger.warning("VS Generation L1 retry: %s", e)
        try:
            return await _generate_with_vs_inner(query, config, llm_client, nli_gate, flags)
        except ProviderError as e2:
            logger.warning("VS Generation L2 simplified prompt: %s", e2)
            try:
                return await _generate_with_vs_inner(query, config, llm_client, nli_gate, flags, simplified=True)
            except ProviderError as e3:
                logger.error("VS Generation L3 direct fallback: %s", e3)
                text = await llm_client.generate(user=query)
                cand = GenerationCandidate(text=text, probability=1.0, nli_score=None, selected=True)
                return VSGenerationResult(candidates=[cand], selected=cand)
