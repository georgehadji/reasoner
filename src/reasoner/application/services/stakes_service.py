"""Stakes lookups for application flows: one place that maps a problem to a policy."""

from __future__ import annotations

from reasoner.domain.stakes import StakesDomain, StakesProfile
from reasoner.hypergate.stakes_patterns import match_stakes


def detect_stakes(problem: str) -> StakesProfile:
    domain = match_stakes(problem or "")
    if domain is StakesDomain.NONE:
        return StakesProfile()
    return StakesProfile(domain=domain, confidence=1.0, source="regex")


def stakes_mode() -> str:
    from reasoner.core.settings import settings

    mode = settings.STAKES_POLICY_MODE
    return mode if mode in ("shadow", "active") else "off"


def keep_out_of_memory(problem: str) -> bool:
    """Health questions are special-category data (GDPR Art. 9): never persisted to Neuro.

    Unconditional, not gated by STAKES_POLICY_MODE: privacy does not wait for a rollout.
    """
    return detect_stakes(problem).domain is StakesDomain.HEALTH
