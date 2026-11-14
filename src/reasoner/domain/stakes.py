"""Stakes value objects: how costly a wrong answer is (health, law, finance).

Pure and stdlib-only, so `domain/` stays dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class StakesDomain(StrEnum):
    HEALTH = "health"
    LEGAL = "legal"
    FINANCIAL = "financial"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Jurisdiction:
    country: str | None = None  # ISO 3166-1 alpha-2, e.g. "GR"
    as_of: date | None = None


@dataclass(frozen=True, slots=True)
class StakesProfile:
    domain: StakesDomain = StakesDomain.NONE
    confidence: float = 0.0
    jurisdiction: Jurisdiction = Jurisdiction()
    missing_facts: tuple[str, ...] = ()  # decisive facts the question lacks
    source: str = "regex"  # "regex" | "llm"

    @property
    def is_high(self) -> bool:
        return self.domain is not StakesDomain.NONE

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain.value,
            "confidence": self.confidence,
            "country": self.jurisdiction.country,
            "as_of": self.jurisdiction.as_of.isoformat() if self.jurisdiction.as_of else None,
            "missing_facts": list(self.missing_facts),
            "source": self.source,
        }
