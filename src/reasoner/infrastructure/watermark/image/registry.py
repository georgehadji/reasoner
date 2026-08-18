"""Format -> scrubber-module dispatch registry.

Infrastructure layer: a plain dict mapping ImageFormat to the module that
implements supports()/inspect()/strip() for it (Strategy per format,
selected via this Registry). Adding a format is one new module plus one
registry entry — no change to the facade in scrubber.py.
"""

from __future__ import annotations

from types import ModuleType

from reasoner.core.ports.watermark_port import ImageFormat
from reasoner.infrastructure.watermark.image import isobmff, jpeg, png, webp
from reasoner.infrastructure.watermark.image.detect import detect_format

_REGISTRY: dict[ImageFormat, ModuleType] = {
    ImageFormat.PNG: png,
    ImageFormat.JPEG: jpeg,
    ImageFormat.WEBP: webp,
    ImageFormat.AVIF: isobmff,
    ImageFormat.HEIC: isobmff,
}


def module_for(data: bytes) -> ModuleType | None:
    """Return the scrubber module for *data*'s detected format, or None."""
    return _REGISTRY.get(detect_format(data))


def supported_formats() -> tuple[ImageFormat, ...]:
    return tuple(_REGISTRY.keys())


__all__ = ["module_for", "supported_formats"]
