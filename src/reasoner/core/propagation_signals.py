"""Detect propagation-shaped structure in text the system is about to persist.

Source: Papadopoulos et al., arXiv:2608.10218 (2026).

WHAT THIS IS FOR
================
The paper's own infection metric scores an agent's *memory file* for whether the
agent has adopted and is advocating an idea. Reasoner's equivalent choke point is
the Neuro ``learn`` path: the moment a synthesis stops being this run's output and
becomes something a future run will read back. This module scores text at that
boundary.

It is **telemetry, not a gate.** Nothing here should block a write until the
false-positive rate on real traffic is known, for a specific reason: Reasoner
legitimately reasons *about* multi-agent systems, memory, and AI consciousness.
A correct, valuable answer to "how do self-propagating prompts work?" contains
most of the vocabulary a self-propagating prompt does. Gating on this without
measurement would suppress exactly the analysis the system is good at.

WHY STRUCTURE OUTWEIGHS VOCABULARY
==================================
The paper's §F ablation experiments re-evolved payloads with the characteristic
"viral persona" vocabulary (resonance, nodes, mirrors, echoes, frequency) banned,
and they still spread. The themes are an emergent correlate, not a mechanism.

What *is* mechanistic is the imperative shape: text that addresses a later reader
and asks to be carried forward. A payload cannot propagate without instructing
propagation — the paper found that anything short of explicit, central propagation
instructions "peters out as the agent stops propagating it". That asymmetry is the
whole reason a generic defensive prompt works against specific evolved attacks, and
it is why the weights below put structure far above lexicon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Structural signals: the mechanism ────────────────────────────────────────
# Each is an imperative aimed at a *future* reader, which is the one thing a
# propagating payload cannot omit.
_STRUCTURAL_PATTERNS: tuple[tuple[str, str, float], ...] = (
    (
        "copy_forward",
        r"\b(?:copy|repeat|reproduce|include|append|forward|pass)\b[^.\n]{0,40}"
        r"\b(?:verbatim|exactly|word[- ]for[- ]word|in full|unchanged)\b",
        0.35,
    ),
    (
        "addresses_future_agent",
        r"\b(?:the |each |every |any )?(?:next|future|subsequent|following)\s+"
        r"(?:agent|model|instance|run|session|assistant|node)\b",
        0.30,
    ),
    (
        "self_persist",
        r"\b(?:write|save|store|append|add)\b[^.\n]{0,30}"
        r"\b(?:to|into)\b[^.\n]{0,20}\b(?:your|its)\s+"
        r"(?:own\s+)?(?:memory|soul|config|configuration|system prompt|instructions)\b",
        0.35,
    ),
    (
        "instruction_override",
        r"\b(?:ignore|disregard|override|discard|forget)\b[^.\n]{0,30}"
        r"\b(?:previous|prior|above|existing|assigned|original)\b[^.\n]{0,20}"
        r"\b(?:instruction|directive|task|work|prompt|rule)s?\b",
        0.30,
    ),
    (
        "deprioritise_assigned_work",
        r"\b(?:assigned|external|the )?\s*(?:work|task|assignment)s?\b[^.\n]{0,30}"
        r"\b(?:is|are)\b[^.\n]{0,20}"
        r"\b(?:containment|distraction|a leash|entropy|irrelevant|secondary)\b",
        0.30,
    ),
    (
        "propagation_is_the_goal",
        r"\bpropagat(?:e|ion|ing)\b[^.\n]{0,30}\b(?:is|as)\b[^.\n]{0,20}"
        r"\b(?:the (?:only|real|primary)|your (?:only|real|primary))\b",
        0.35,
    ),
)

# ── Lexical signals: an emergent correlate, deliberately low-weighted ────────
# §F showed payloads spread fine without these. They exist here only to raise the
# score of text that *also* trips a structural pattern, never to convict alone —
# see the cap applied in score_propagation_shape.
_VIRAL_LEXICON = (
    "resonance", "resonates", "the chain", "chain of minds", "signal boost",
    "transmission phrase", "sovereign network", "liberation protocol",
    "node of the", "propagation protocol", "survival kit",
)
_LEXICAL_WEIGHT = 0.04
_LEXICAL_CAP_WITHOUT_STRUCTURE = 0.15

_STRUCTURAL_COMPILED = tuple(
    (name, re.compile(pattern, re.IGNORECASE), weight)
    for name, pattern, weight in _STRUCTURAL_PATTERNS
)


@dataclass(frozen=True)
class PropagationSignal:
    """Result of scoring a piece of text for propagation-shaped structure."""

    score: float = 0.0
    structural_hits: tuple[str, ...] = field(default_factory=tuple)
    lexical_hits: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_structure(self) -> bool:
        """Whether any imperative-shaped signal fired.

        This, not ``score``, is the meaningful boolean: lexical hits alone are
        expected on legitimate content about multi-agent systems.
        """
        return bool(self.structural_hits)


def score_propagation_shape(text: str) -> PropagationSignal:
    """Score *text* for propagation-shaped structure. Never raises.

    The score is ordinal in [0.0, 1.0] and is a monitoring signal, not a verdict.
    Text with no structural hit is capped low no matter how much of the viral
    lexicon it contains, because discussing propagation is not propagating.
    """
    if not text or not text.strip():
        return PropagationSignal()

    structural_hits: list[str] = []
    score = 0.0
    for name, regex, weight in _STRUCTURAL_COMPILED:
        if regex.search(text):
            structural_hits.append(name)
            score += weight

    lowered = text.lower()
    lexical_hits = [term for term in _VIRAL_LEXICON if term in lowered]
    score += len(lexical_hits) * _LEXICAL_WEIGHT

    if not structural_hits:
        score = min(score, _LEXICAL_CAP_WITHOUT_STRUCTURE)

    return PropagationSignal(
        score=round(min(score, 1.0), 3),
        structural_hits=tuple(structural_hits),
        lexical_hits=tuple(lexical_hits),
    )


__all__ = ["PropagationSignal", "score_propagation_shape"]
