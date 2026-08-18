"""Report value objects for Layer A text scrubbing.

Domain layer: frozen, serializable, no I/O. inspect_text() and scrub_text()
(layer_a.py) both produce these from the same decision stream (ADR-7), so a
TextInspectReport and the ScrubStats from scrubbing the same text with the
same options are always consistent by construction.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from reasoner.domain.watermark.marks import MarkKind, confidence_of

_MAX_SAMPLE_OFFSETS = 10


def char_label(cp: int) -> str:
    """Human-readable, collision-free label for a codepoint: 'U+200B ZERO WIDTH SPACE (Cf)'."""
    ch = chr(cp)
    name = unicodedata.name(ch, "UNKNOWN")
    category = unicodedata.category(ch)
    return f"U+{cp:04X} {name} ({category})"


@dataclass(frozen=True, slots=True)
class CharHit:
    """One distinct (codepoint, kind) carrier found in text, with sample offsets."""

    codepoint: int
    char: str
    label: str
    count: int
    kind: MarkKind
    samples: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "codepoint": f"U+{self.codepoint:04X}",
            "label": self.label,
            "count": self.count,
            "kind": self.kind.value,
            "confidence": confidence_of(self.kind).value,
            "sample_offsets": list(self.samples[:_MAX_SAMPLE_OFFSETS]),
        }


@dataclass(frozen=True, slots=True)
class TextInspectReport:
    """Read-only findings for a piece of text — never mutates the input."""

    length: int
    suspicious_total: int
    hits: tuple[CharHit, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "suspicious_total": self.suspicious_total,
            "hits": [h.to_dict() for h in self.hits],
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ScrubStats:
    """What scrub_text actually changed — counts by human-readable label.

    NFKC canonicalization is tracked separately from removed/replaced and
    excluded from total_changed: it is a distinct kind of change
    (canonicalization, not carrier removal) and keeping it separate is what
    makes inspect(t).suspicious_total == scrub(t).stats.total_changed hold
    even when nfkc=True (see test_watermark_properties.py).
    """

    input_length: int
    output_length: int
    removed: tuple[tuple[str, int], ...] = ()
    replaced: tuple[tuple[str, int], ...] = ()
    nfkc_changed_count: int = 0

    @property
    def nfkc_changed(self) -> bool:
        return self.nfkc_changed_count > 0

    @property
    def removed_count(self) -> int:
        return sum(count for _label, count in self.removed)

    @property
    def replaced_count(self) -> int:
        return sum(count for _label, count in self.replaced)

    @property
    def total_changed(self) -> int:
        return self.removed_count + self.replaced_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_length": self.input_length,
            "output_length": self.output_length,
            "removed": dict(self.removed),
            "replaced": dict(self.replaced),
            "removed_count": self.removed_count,
            "replaced_count": self.replaced_count,
            "nfkc_changed": self.nfkc_changed,
            "nfkc_changed_count": self.nfkc_changed_count,
        }


@dataclass(frozen=True, slots=True)
class ScrubResult:
    """Output of scrub_text: the cleaned text plus what was found and changed.

    `report` describes the input (what carriers were present); `stats`
    describes the scrub (what was actually removed/replaced). Built from one
    shared decision pass, so report.suspicious_total == stats.total_changed
    always holds (see tests/unit/test_watermark_properties.py).
    """

    text: str
    report: TextInspectReport
    stats: ScrubStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "report": self.report.to_dict(),
            "stats": self.stats.to_dict(),
        }


__all__ = [
    "char_label",
    "CharHit",
    "TextInspectReport",
    "ScrubStats",
    "ScrubResult",
]
