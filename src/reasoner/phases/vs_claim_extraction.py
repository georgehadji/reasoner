"""VS Claim Extraction stage — ClaimExtractionStage."""
from __future__ import annotations

import asyncio
from collections import Counter
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from reasoner.phases.vs_generation import GenerationCandidate
from reasoner.vs_config import VSFeatureFlags


class _LLMClient(Protocol):
    async def generate(self, *, system: str = "", user: str = "") -> str: ...


class ClaimExtractionMode(str, Enum):
    SINGLE = "single"
    UNION = "union"
    CONSENSUS = "consensus"


class VSClaimExtractionConfig(BaseModel):
    mode: ClaimExtractionMode = ClaimExtractionMode.SINGLE


class ExtractedClaimSet(BaseModel):
    claims: list[str]
    source: str
    vs_metadata: dict[str, Any] = Field(default_factory=dict)


async def _extract_claims(text: str, llm_client: _LLMClient | None) -> list[str]:
    """Extract factual claims from text using LLM, with sentence-split fallback."""
    from reasoner.parsing import extract_json_list

    fallback = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if llm_client is None:
        return fallback

    try:
        prompt = f"Extract factual claims from this text as a JSON list of strings. Return ONLY the JSON list.\nText: {text}"
        raw = await llm_client.generate(user=prompt)
        claims = extract_json_list(raw)
        if not claims:
            return fallback
        return [str(c) for c in claims]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Claim extraction failed: {e}. Falling back to sentence split.")
        return fallback


async def extract_claims_from_vs_candidates(
    candidates: list[GenerationCandidate],
    config: VSClaimExtractionConfig,
    llm_client: _LLMClient,
    flags: VSFeatureFlags,
) -> ExtractedClaimSet:
    if not flags.claim_extraction:
        return ExtractedClaimSet(claims=[c.text for c in candidates], source="direct")

    if not candidates:
        return ExtractedClaimSet(claims=[], source="direct")

    if config.mode == ClaimExtractionMode.SINGLE:
        return ExtractedClaimSet(claims=[candidates[0].text], source="single")

    if config.mode == ClaimExtractionMode.UNION:
        tasks = [asyncio.create_task(_extract_claims(c.text, llm_client)) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_claims: list[str] = []
        seen: set[str] = set()
        for res in results:
            if isinstance(res, Exception):
                import logging
                logging.getLogger(__name__).error(f"Task failed in UNION claim extraction: {res}")
                continue
            for claim in res:
                key = claim.lower().strip()
                if key not in seen:
                    seen.add(key)
                    all_claims.append(claim)
        return ExtractedClaimSet(claims=all_claims, source="union")

    # CONSENSUS
    tasks = [asyncio.create_task(_extract_claims(c.text, llm_client)) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and flatten
    valid_results: list[list[str]] = []
    for res in results:
        if isinstance(res, Exception):
            import logging
            logging.getLogger(__name__).error(f"Task failed in CONSENSUS claim extraction: {res}")
            continue
        valid_results.append(res)

    claim_counts = Counter(claim.lower().strip() for sublist in valid_results for claim in sublist)
    consensus = [claim for sublist in valid_results for claim in sublist if claim_counts[claim.lower().strip()] > len(candidates) / 2]
    # Deduplicate while preserving first-seen order
    seen: set[str] = set()
    deduped: list[str] = []
    for claim in consensus:
        key = claim.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(claim)
    return ExtractedClaimSet(claims=deduped, source="consensus")

