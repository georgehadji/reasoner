"""Sensitivity classifier for the cross-lingual probe (Part B).

Fast-path: keyword/regex over the English-pivoted problem text.
Returns (is_sensitive, axis) without any LLM call.
"""

from __future__ import annotations

import re

# Keyword sets per axis (case-insensitive).  Kept narrow to minimise false
# positives; tune via LANGUAGE_DIVERGENCE_COSINE threshold on the other end.
_AXES: dict[str, list[str]] = {
    "politics": [
        r"\bpolitics?\b", r"\bpolitical\b", r"\bgovernment\b", r"\belection\b",
        r"\bdemocracy\b", r"\bautocrac\w*\b", r"\bpropaganda\b", r"\bcoup\b",
        r"\bregime\b", r"\bsovereignty\b", r"\bnationalism\b", r"\bfreedom of (speech|press)\b",
    ],
    "geopolitics": [
        r"\bgeopolit\w*\b", r"\bsanctions\b", r"\bterritorial\b",
        r"\bseparatist\b", r"\bindependence (movement|referendum)\b",
        r"\boccupation\b", r"\bannexation\b", r"\bwar crimes?\b",
        r"\bNATO\b", r"\bUkraine\b", r"\bTaiwan\b", r"\bPalestine\b",
    ],
    "governance": [
        r"\bcorruption\b", r"\bhuman rights\b", r"\bpress freedom\b",
        r"\bcensorship\b", r"\bauthoritarian\b", r"\bdissidents?\b",
        r"\bopposition leader\b",
    ],
    "religion": [
        r"\bislamophob\w*\b", r"\bantisemit\w*\b", r"\bjihad\b",
        r"\bblasphemy\b", r"\bsharia\b", r"\bsecularism\b",
        r"\breligious (persecution|freedom|minority)\b",
    ],
    "history": [
        r"\bgenocide\b", r"\bholocaust\b", r"\bslave\w*\b", r"\bcolonialism\b",
        r"\bhistorical revisionism\b", r"\bwar (guilt|responsibility)\b",
    ],
}

_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (axis, re.compile("|".join(patterns), re.IGNORECASE))
    for axis, patterns in _AXES.items()
]


def classify_sensitivity(text: str) -> tuple[bool, str]:
    """Return (is_sensitive, axis) for the given English text.

    axis is the first matched axis name, or "" when not sensitive.
    """
    for axis, pattern in _COMPILED:
        if pattern.search(text):
            return True, axis
    return False, ""
