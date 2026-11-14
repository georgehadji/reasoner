"""Stakes lookups for application flows: one place that maps a problem to a policy."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from reasoner.domain.stakes import KNOWN_COUNTRIES, StakesDomain, StakesProfile
from reasoner.hypergate.stakes_patterns import fold_text, match_stakes


def detect_stakes(problem: str) -> StakesProfile:
    domain = match_stakes(problem or "")
    if domain is StakesDomain.NONE:
        return StakesProfile()
    return StakesProfile(domain=domain, confidence=1.0, source="regex")


def stakes_mode() -> str:
    from reasoner.core.settings import settings

    mode = settings.STAKES_POLICY_MODE
    return mode if mode in ("shadow", "active") else "off"


_COUNTRY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (cc, re.compile(fold_text(p)))
    for cc, p in (
        ("GR", r"\b(greece|greek|ελλαδα\w*|ελλαδ\w*|ελληνικ\w*)"),
        ("US", r"\b(united states|u\.s\.|usa|american)\b"),
        ("GB", r"\b(united kingdom|england|british|uk)\b"),
        ("DE", r"\b(germany|german|γερμανι\w*)"),
        ("FR", r"\b(france|french|γαλλι\w*)"),
        ("CY", r"\b(cyprus|κυπρο\w*)"),
    )
)


def _from_text(problem: str, _explicit: str | None) -> str | None:
    """Country named in the question itself, only when exactly one is named."""
    folded = fold_text(problem)
    hits = [cc for cc, pat in _COUNTRY_PATTERNS if pat.search(folded)]
    return hits[0] if len(hits) == 1 else None


def _explicit(_problem: str, explicit: str | None) -> str | None:
    code = (explicit or "").strip().upper()
    return code if code in KNOWN_COUNTRIES else None


# Chain of Responsibility: first non-None wins. An explicit request value beats
# the question's own text; no account default exists (decided 2026-11-14).
_RESOLVERS = (_explicit, _from_text)


def resolve_jurisdiction(problem: str, explicit: str | None = None) -> str | None:
    for resolve in _RESOLVERS:
        country = resolve(problem or "", explicit)
        if country is not None:
            return country
    return None


def scope_for(problem: str, explicit: str | None = None, today: date | None = None) -> dict:
    """The jurisdiction and date a high-stakes answer is scoped to."""
    return {
        "jurisdiction": resolve_jurisdiction(problem, explicit),
        "as_of": (today or datetime.now(UTC).date()).isoformat(),
    }


def scope_prompt_block(domain: StakesDomain, scope: dict) -> str:
    """Instruction text for the synthesis prompt. Built only from fixed values."""
    where = scope.get("jurisdiction") or "not stated"
    return (
        f"\nHIGH-STAKES SCOPE ({domain.value}): jurisdiction {where}; as of {scope['as_of']}. "
        "State which rules apply as of this date and name the source of each rule. "
        "If the jurisdiction is not stated, say that the answer may differ by country "
        "and do not assume one. Label a claim VERIFIED only when a primary source backs it.\n"
    )


def keep_out_of_memory(problem: str) -> bool:
    """Health questions are special-category data (GDPR Art. 9): never persisted to Neuro.

    Unconditional, not gated by STAKES_POLICY_MODE: privacy does not wait for a rollout.
    """
    return detect_stakes(problem).domain is StakesDomain.HEALTH
