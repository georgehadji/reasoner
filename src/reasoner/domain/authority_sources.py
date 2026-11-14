"""Authority registry: which hosts count as a primary source per domain and country.

Declarative data plus one pure lookup. An entry counts only once it carries a
``reviewed_on`` date: the seed rows below are candidates awaiting owner review
(plan §2.2), so until they are reviewed every lookup returns NONE and a
high-stakes claim is capped at HYPOTHESIS. That fails safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from urllib.parse import urlsplit

from reasoner.domain.stakes import StakesDomain


class AuthorityTier(IntEnum):
    NONE = 0
    SECONDARY = 1  # peer-reviewed, official statistics
    PRIMARY = 2  # statute, regulator, clinical guideline body


@dataclass(frozen=True, slots=True)
class AuthorityEntry:
    host: str  # registrable host; subdomains match
    domain: StakesDomain
    countries: tuple[str, ...]  # ISO codes; "*" = any
    tier: AuthorityTier
    reviewed_on: date | None = None  # None = candidate, not yet counted


_H, _L, _F = StakesDomain.HEALTH, StakesDomain.LEGAL, StakesDomain.FINANCIAL
_P, _S = AuthorityTier.PRIMARY, AuthorityTier.SECONDARY

REGISTRY: tuple[AuthorityEntry, ...] = (
    AuthorityEntry("who.int", _H, ("*",), _P),
    AuthorityEntry("ema.europa.eu", _H, ("EU", "GR"), _P),
    AuthorityEntry("eof.gr", _H, ("GR",), _P),
    AuthorityEntry("cdc.gov", _H, ("US",), _P),
    AuthorityEntry("fda.gov", _H, ("US",), _P),
    AuthorityEntry("nih.gov", _H, ("*",), _S),
    AuthorityEntry("eur-lex.europa.eu", _L, ("EU", "GR"), _P),
    AuthorityEntry("et.gr", _L, ("GR",), _P),
    AuthorityEntry("esma.europa.eu", _F, ("EU", "GR"), _P),
    AuthorityEntry("aade.gr", _F, ("GR",), _P),
    AuthorityEntry("bankofgreece.gr", _F, ("GR",), _P),
    AuthorityEntry("sec.gov", _F, ("US",), _P),
    AuthorityEntry("irs.gov", _F, ("US",), _P),
)


def _host(url: str) -> str:
    return (urlsplit(url.strip()).hostname or "").lower()


def authority_tier(
    url: str,
    domain: StakesDomain,
    country: str | None,
    registry: tuple[AuthorityEntry, ...] = REGISTRY,
) -> AuthorityTier:
    """Best reviewed tier for ``url`` in ``domain``/``country``.

    An unknown country matches only "*" rows.
    """
    host = _host(url)
    best = AuthorityTier.NONE
    for e in registry:
        if e.reviewed_on is None or e.domain is not domain:
            continue
        if "*" not in e.countries and (country is None or country.upper() not in e.countries):
            continue
        if host == e.host or host.endswith("." + e.host):
            best = max(best, e.tier)
    return best


def rank_by_authority(
    results: list[dict],
    domain: StakesDomain,
    country: str | None,
    registry: tuple[AuthorityEntry, ...] = REGISTRY,
) -> list[dict]:
    """Stable sort of search results (dicts with "url"), highest tier first."""
    return sorted(
        results,
        key=lambda r: -authority_tier(str(r.get("url", "")), domain, country, registry),
    )
