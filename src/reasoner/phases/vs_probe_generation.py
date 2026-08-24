"""VS Probe Generation stage — IntentConsistencyStage."""
from __future__ import annotations

import difflib
from typing import Any, Protocol

from pydantic import BaseModel, Field

from reasoner.reasoner_verbalized_sampling import VSMode, build_vs_prompt, parse_vs_response
from reasoner.reasoner_vs_constants import (
    LOG_VS_PROBE_COUNT,
    LOG_VS_PROBE_DOMAIN,
    VS_K_PROBES,
    VS_PROBE_MIN_SEMANTIC_DISTANCE,
    VS_TAIL_THRESHOLD_RADIOLOGY,
)
from reasoner.vs_config import VSFeatureFlags

DOMAIN_PROBE_TEMPLATES = {
    "radiology": "Generate {k} distinct clinical questions a radiologist would ask about: {query}",
    "legal": "Generate {k} angles a legal analyst would investigate for: {query}",
    "aerospace": "Generate {k} failure-mode probes an aerospace engineer would consider for: {query}",
    "default": "Generate {k} diverse perspectives on: {query}",
}


class _LLMClient(Protocol):
    async def generate(self, *, system: str = "", user: str = "") -> str: ...


class ProbeGenerationConfig(BaseModel):
    domain: str = "default"
    k: int = VS_K_PROBES
    tail_threshold: float = VS_TAIL_THRESHOLD_RADIOLOGY


class ProbeSet(BaseModel):
    probes: list[str]
    source: str = "vs_tail"
    vs_metadata: dict[str, Any] = Field(default_factory=dict)


def _semantic_distance(a: str, b: str) -> float:
    """Simplified semantic distance using sequence matcher (0.0=identical, 1.0=completely different)."""
    return 1.0 - difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def generate_probes_with_vs(
    query: str,
    config: ProbeGenerationConfig,
    llm_client: _LLMClient,
    flags: VSFeatureFlags,
) -> ProbeSet:
    if not flags.probe_generation:
        return ProbeSet(probes=[query], source="direct")

    system, user = build_vs_prompt(query, VSMode.TAIL, config.k)
    raw = await llm_client.generate(system=system, user=user)
    result = parse_vs_response(raw)

    # Identity filter: remove probes identical to query
    probes = [c.text for c in result.candidates if c.text.lower() != query.lower()]

    # Semantic distance filter: keep probes sufficiently different
    probes = [p for p in probes if _semantic_distance(p, query) >= VS_PROBE_MIN_SEMANTIC_DISTANCE]

    if len(probes) < 2:
        # Fallback to STANDARD mode
        system, user = build_vs_prompt(query, VSMode.STANDARD, config.k)
        raw = await llm_client.generate(system=system, user=user)
        result = parse_vs_response(raw)
        probes = [c.text for c in result.candidates if c.text.lower() != query.lower()]

    probes = probes[: config.k]
    return ProbeSet(
        probes=probes,
        source="vs_tail",
        vs_metadata={
            LOG_VS_PROBE_DOMAIN: config.domain,
            LOG_VS_PROBE_COUNT: len(probes),
        },
    )
