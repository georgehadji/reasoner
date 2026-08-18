"""Protected-span detection for Layer A Unicode scrubbing (ADR-6).

Reasoner output carries URLs, citations, and code fences that must not be
touched by *normalizing* decisions (confusable substitution, NFKC). Carrier
stripping (invisible/format Unicode) ignores these spans by design -- an
invisible character inside a URL or code fence is still a carrier, and inside
a code fence it is a correctness bug, not a legitimate use.

Domain layer: pure regex + interval arithmetic, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+")
# Mirrors the link-extraction convention already used in
# application/flows/writing_phases.py: only protect an http(s) target, not
# arbitrary parenthetical content after a markdown link.
_MD_LINK_TARGET_RE = re.compile(r"\[[^\]]*\]\((https?://[^)]+)\)")


@dataclass(frozen=True, slots=True)
class ProtectedSpans:
    """Half-open [start, end) character-index intervals, merged and sorted."""

    intervals: tuple[tuple[int, int], ...] = ()

    def covers(self, index: int) -> bool:
        return any(start <= index < end for start, end in self.intervals)


def _merge(intervals: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not intervals:
        return ()
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def detect_protected_spans(text: str) -> ProtectedSpans:
    """Find fenced/inline code, bare URLs, and markdown link targets in *text*."""
    intervals: list[tuple[int, int]] = []
    for pattern in (_FENCED_CODE_RE, _INLINE_CODE_RE, _URL_RE):
        intervals.extend(m.span() for m in pattern.finditer(text))
    for m in _MD_LINK_TARGET_RE.finditer(text):
        intervals.append(m.span(1))
    return ProtectedSpans(_merge(intervals))


__all__ = ["ProtectedSpans", "detect_protected_spans"]
