"""
ReasoningMethod — single source of truth for method identifiers.

The wire format (used in preset IDs, SSE payloads, UI) is hyphenated:
    ``pre-mortem``, ``self-discover``

The Python identifier / module suffix (used for attribute and module lookups) is
underscored:
    ``pre_mortem``, ``self_discover``

``StrEnum`` makes both derivations from one value, eliminating the
dual-spelling bug that broke 4 presets and ``test_cross_language.py``.

Design: ``StrEnum`` (not ``Enum``) so serialization to JSON/SSE works
unchanged — this is a non-breaking, wire-compatible refactor.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ReasoningMethod(StrEnum):
    """Every supported reasoning method.

    The *value* (hyphenated) is the canonical wire identifier.
    The derived ``module_suffix`` property (underscored) is used for
    Python module / attribute lookups.
    """

    MULTI_PERSPECTIVE = "multi-perspective"
    DEBATE = "debate"
    JURY = "jury"
    RESEARCH = "research"
    SCIENTIFIC = "scientific"
    SOCRATIC = "socratic"
    PRE_MORTEM = "pre-mortem"
    BAYESIAN = "bayesian"
    DIALECTICAL = "dialectical"
    ANALOGICAL = "analogical"
    DELPHI = "delphi"
    COVE = "cove"
    SOT = "sot"
    TOT = "tot"
    POT = "pot"
    SELF_DISCOVER = "self-discover"
    WRITING = "writing"
    ARTICLE = "article"
    CODING = "coding"
    BRAINSTORMING = "brainstorming"
    SUBAGENT = "subagent"
    CROSS_LANGUAGE = "cross-language"
    ITERATIVE_CRITIQUE = "iterative-critique"
    IMAGE_GEN = "image-gen"

    # ── helpers ─────────────────────────────────────────────────────

    @property
    def module_suffix(self) -> str:
        """Python-safe identifier, e.g. ``pre_mortem``, ``self_discover``."""
        return self.value.replace("-", "_")

    @classmethod
    def from_module_suffix(cls, suffix: str) -> ReasoningMethod:
        """Reverse lookup from underscored form (e.g. ``pre_mortem``)."""
        lookup = {m.module_suffix: m for m in cls}
        return lookup[suffix]

    @classmethod
    def valid_methods(cls) -> set[str]:
        """Set of valid hyphenated identifiers — matches validator expectations."""
        return {m.value for m in cls}

    @classmethod
    def valid_suffixes(cls) -> set[str]:
        """Set of valid underscored identifiers — matches runtime expectations."""
        return {m.module_suffix for m in cls}


# ── convenience constant ─────────────────────────────────────────

VALID_METHODS: Final[set[str]] = ReasoningMethod.valid_methods()
VALID_METHOD_SUFFIXES: Final[set[str]] = ReasoningMethod.valid_suffixes()
