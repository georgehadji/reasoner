"""Layer A: edit-based Unicode watermark inspection and scrubbing.

Pure domain module (bottom of the .importlinter layer stack) -- imports
nothing outside reasoner.domain and the standard library, so every layer
above can depend on it without a new architecture exception.

    from reasoner.domain.watermark import inspect_text, scrub_text, ScrubOptions

See docs/plans/watermark-removal-integration.md for the full design (ADR-1
through ADR-10) and docs/plans/watermark-removal-integration.md#part-v for
the module-by-module specification.
"""

from __future__ import annotations

from reasoner.domain.watermark.layer_a import (
    DEFAULT_OPTIONS,
    Action,
    Decision,
    inspect_text,
    scrub_text,
)
from reasoner.domain.watermark.marks import MarkConfidence, MarkKind
from reasoner.domain.watermark.report import CharHit, ScrubResult, ScrubStats, TextInspectReport
from reasoner.domain.watermark.rules import ScrubOptions
from reasoner.domain.watermark.spans import ProtectedSpans, detect_protected_spans

__all__ = [
    "inspect_text",
    "scrub_text",
    "ScrubOptions",
    "DEFAULT_OPTIONS",
    "Action",
    "Decision",
    "MarkKind",
    "MarkConfidence",
    "CharHit",
    "TextInspectReport",
    "ScrubStats",
    "ScrubResult",
    "ProtectedSpans",
    "detect_protected_spans",
]
