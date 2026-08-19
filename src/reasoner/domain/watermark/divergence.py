"""Bigram-Jaccard lexical divergence scoring for Layer B rewrite candidates.

Ported verbatim from the reference repo's `rewrite_text.py`
(`_lexical_divergence`, `_select_candidate`) -- pure, deterministic, no I/O,
belongs in the domain layer per ADR-1 (domain-layer purity).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_LENGTH_DRIFT_PENALTY = 0.15
_LENGTH_DRIFT_HIGH = 2.0
_LENGTH_DRIFT_LOW = 0.5


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:], strict=False))


def lexical_divergence(original: str, candidate: str) -> float:
    """Bigram Jaccard distance: 0.0 identical, 1.0 fully different."""
    a, b = _tokens(original), _tokens(candidate)
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    ba, bb = _bigrams(a), _bigrams(b)
    union = ba | bb
    if not union:
        return 0.0
    return 1.0 - len(ba & bb) / len(union)


@dataclass(frozen=True, slots=True)
class Selection:
    text: str
    index: int
    scores: tuple[float, ...]


def select_most_diverged(original: str, candidates: Sequence[str]) -> Selection:
    """Pick the most lexically diverged candidate.

    -0.15 penalty for candidates whose length is >2x or <0.5x the original --
    a rewrite that's wildly longer or shorter is more likely truncated or
    padded than genuinely diverged.
    """
    scores: list[float] = []
    for cand in candidates:
        score = lexical_divergence(original, cand)
        if original:
            ratio = len(cand) / len(original)
            if ratio > _LENGTH_DRIFT_HIGH or ratio < _LENGTH_DRIFT_LOW:
                score -= _LENGTH_DRIFT_PENALTY
        scores.append(score)
    best_idx = max(range(len(candidates)), key=lambda i: scores[i])
    return Selection(text=candidates[best_idx], index=best_idx, scores=tuple(scores))


__all__ = ["lexical_divergence", "select_most_diverged", "Selection"]
