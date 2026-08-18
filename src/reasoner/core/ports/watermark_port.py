"""Core ports for AI-mark scrubbing on non-text media (images) and optional
pixel-domain backends.

Hexagonal DDD port layer — infrastructure adapters implement these; the
application service depends only on the Protocol, never a concrete adapter.
Mirrors core/ports/code_executor.py and core/ports/translation_port.py.

Paper grounding: docs/plans/watermark-removal-integration.md ADR-2 (ports in
core, adapters in infrastructure), ADR-3 (bytes in, bytes out), ADR-8 (pixel
removal is a port + Null Object, not an implementation).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from reasoner.domain.watermark.marks import MarkConfidence


class ImageFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    AVIF = "avif"
    HEIC = "heic"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MarkFinding:
    """One provenance/AI-marker finding in an image or container.

    Reuses domain.watermark.marks.MarkConfidence -- that enum's four tiers
    were declared to cover both text and file/image findings under one
    vocabulary (see its docstring); the image class is the one that actually
    uses all four (CONFIRMED for a parsed C2PA/JUMBF structure,
    LIKELY_FALSE_POSITIVE for a raw byte-scan hit that can collide with
    compressed pixel data).
    """

    description: str
    confidence: MarkConfidence

    def to_dict(self) -> dict[str, str]:
        return {"description": self.description, "confidence": self.confidence.value}


@dataclass(frozen=True, slots=True)
class ImageInspectReport:
    """Read-only findings for one image — never mutates the input bytes."""

    format: ImageFormat
    has_c2pa: bool
    has_ai_metadata: bool
    findings: tuple[MarkFinding, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format.value,
            "has_c2pa": self.has_c2pa,
            "has_ai_metadata": self.has_ai_metadata,
            "findings": [f.to_dict() for f in self.findings],
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ScrubOutcome:
    """Result of a scrub operation (image metadata strip, or — Phase 6+ —
    pixel-domain removal).

    `degraded`/`degraded_reason` mirror TranslationResult
    (core/ports/translation_port.py): a scrub that silently no-ops must be
    distinguishable from one that genuinely found and removed nothing. PDF
    metadata tools that report success while leaving the original bytes
    recoverable are the cautionary example (Part I.5 of the integration
    plan) — "exit 0" is not evidence of removal.
    """

    data: bytes
    actions: tuple[str, ...] = ()
    findings: tuple[MarkFinding, ...] = ()
    residual: bool = False  # re-inspection after the scrub still found something
    degraded: bool = False
    degraded_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "findings": [f.to_dict() for f in self.findings],
            "residual": self.residual,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "bytes_out": len(self.data),
        }


@runtime_checkable
class ImageMarkScrubberPort(Protocol):
    """Port for image container/provenance-metadata inspection and scrubbing.

    Bytes in, bytes out (ADR-3) — Reasoner's images are in-memory data URLs,
    never files, so path handling belongs to a CLI adapter, not this port.
    """

    def supports(self, data: bytes) -> bool:
        """True if *data* is a format this scrubber can inspect/scrub."""
        ...

    def inspect(self, data: bytes) -> ImageInspectReport:
        """Read-only: what provenance/AI markers are present."""
        ...

    def scrub(self, data: bytes, *, strip_all_metadata: bool = True) -> ScrubOutcome:
        """Strip provenance/AI metadata.

        Implementations re-inspect their own output before returning, so
        `residual` on the result is never a guess.
        """
        ...


@runtime_checkable
class PixelScrubberPort(Protocol):
    """Port for optional pixel-domain watermark removal (ADR-8).

    Bound to a Null Object by default — CtrlRegen/DiffusionPurification-class
    backends need ~10 GB of model weights and a GPU, which does not belong in
    Reasoner's runtime or container image. An HTTP adapter to an external
    service is the intended real implementation; this port exists so the
    application layer and capability reporting never special-case "backend
    absent" versus "backend present but nothing to remove."
    """

    async def available(self) -> bool:
        """False when unbound/unconfigured.

        Callers must fail closed (report the capability as absent) rather
        than attempt a call anyway.
        """
        ...

    async def scrub(self, data: bytes, *, strength: float = 0.25) -> ScrubOutcome: ...


__all__ = [
    "ImageFormat",
    "MarkFinding",
    "ImageInspectReport",
    "ScrubOutcome",
    "ImageMarkScrubberPort",
    "PixelScrubberPort",
]
