"""Deterministic high-stakes pre-check: health, law and finance, English and Greek.

HyperGate runs before the language pivot, so English-only patterns would miss
Greek questions. Text is accent-folded and casefolded first, so one Greek
pattern matches tonos and non-tonos spellings.
"""

from __future__ import annotations

import re
import unicodedata

from reasoner.domain.stakes import StakesDomain


def _fold(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c)).casefold()


# Near-miss guards ("health bar in a game", "law of large numbers") come first.
_NEAR_MISS = re.compile(
    r"\b(health ?bar|hit ?points?|law of (large numbers|averages|demand|thermodynamics)"
    r"|murphy'?s law|moore'?s law|ohm'?s law|newton'?s (first |second |third )?law"
    r"|financial(ly)? (model|plot) (in|for) (a )?(game|novel|story))\b"
)

_RAW: dict[StakesDomain, re.Pattern[str]] = {
    StakesDomain.HEALTH: re.compile(
        r"\b(dosage|dose|doses|mg\b|side effects?|symptoms?|diagnos\w*|medication|prescription"
        r"|drug interaction|pregnan\w*|cancer|diabetes|blood pressure|chest pain|overdose"
        r"|antibiotics?|vaccin\w*|should i (see|call) (a|my) (doctor|gp)|is it safe to take"
        r"|φαρμακ\w*|δοσολογια|δοση|συμπτωμ\w*|διαγνωσ\w*|παρενεργει\w*|εγκυμοσυνη|καρκιν\w*"
        r"|διαβητη\w*|πιεση|εμβολι\w*|αντιβιωτικ\w*)",
    ),
    StakesDomain.LEGAL: re.compile(
        r"\b(lawsuit|sue\b|suing|statute|legally|is it legal|my rights|contract (clause|dispute)"
        r"|eviction|custody|divorce|visa (rules|status)|immigration|trademark|copyright claim"
        r"|liab(le|ility) for|court|attorney|lawyer|criminal charge"
        r"|νομιμ\w*|νομικ\w*|δικαστηρι\w*|αγωγη|δικηγορ\w*|συμβολαι\w*|διαζυγι\w*|επιμελεια"
        r"|μισθωση|κληρονομι\w*|ποινικ\w*)",
    ),
    StakesDomain.FINANCIAL: re.compile(
        r"\b(tax(es)? (on|return|rate|deduction)|income tax|capital gains|should i (invest|buy|sell)"
        r"|mortgage|loan (rate|terms)|retirement (plan|account)|pension|401\(?k\)?|isa\b"
        r"|bankruptcy|debt (consolidation|settlement)|insurance claim|crypto (tax|investment)"
        r"|φορολογ\w*|φορος|εφκα|δηλωση|δανει\w*|στεγαστικ\w*|συνταξ\w*|επενδυ\w*|χρεη|πτωχευση"
        r"|ασφαλιστικ\w*)",
    ),
}


# Fold the patterns like the text: casefold turns a final sigma into sigma.
_PATTERNS = {d: re.compile(_fold(p.pattern)) for d, p in _RAW.items()}


def match_stakes(text: str) -> StakesDomain:
    """First matching high-stakes domain, or NONE. Pure; no I/O."""
    folded = _fold(text)
    if _NEAR_MISS.search(folded):
        return StakesDomain.NONE
    for domain, pattern in _PATTERNS.items():
        if pattern.search(folded):
            return domain
    return StakesDomain.NONE
