"""VS Decomposition stage — QueryDecompositionStage."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from reasoner.reasoner_verbalized_sampling import VSMode, build_vs_prompt, parse_vs_response
from reasoner.reasoner_vs_constants import VS_K_DECOMPOSITION, VS_PARSE_MAX_RETRIES
from reasoner.vs_config import VSFeatureFlags


class _LLMClient(Protocol):
    async def generate(self, *, system: str = "", user: str = "") -> str: ...


class DecompositionVSConfig(BaseModel):
    top_n: int = Field(default=VS_K_DECOMPOSITION, le=VS_K_DECOMPOSITION)


class VSDecompositionResult(BaseModel):
    sub_queries: list[str]
    source: str = "vs"
    vs_metadata: dict[str, Any] = Field(default_factory=dict)


async def decompose_with_vs(
    query: str,
    config: DecompositionVSConfig,
    llm_client: _LLMClient,
    flags: VSFeatureFlags,
) -> VSDecompositionResult:
    if not flags.decomposition:
        return VSDecompositionResult(sub_queries=[query], source="direct")

    system, user = build_vs_prompt(query, VSMode.STANDARD, VS_K_DECOMPOSITION)

    for attempt in range(VS_PARSE_MAX_RETRIES + 1):
        raw = await llm_client.generate(system=system, user=user)
        try:
            result = parse_vs_response(raw)
            sorted_candidates = sorted(result.candidates, key=lambda c: c.probability, reverse=True)
            return VSDecompositionResult(
                sub_queries=[c.text for c in sorted_candidates[: config.top_n]],
                source="vs",
                vs_metadata={"k_used": len(sorted_candidates), "top_n": config.top_n},
            )
        except ValueError:
            if attempt == VS_PARSE_MAX_RETRIES:
                break
            continue

    return VSDecompositionResult(sub_queries=[query], source="direct")
