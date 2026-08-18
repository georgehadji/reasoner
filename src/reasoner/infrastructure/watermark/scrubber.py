"""Default ImageMarkScrubberPort implementation: detect -> strip -> re-inspect.

Infrastructure layer. The one class that actually implements the port;
everything in infrastructure/watermark/image/ is pure functions this facade
composes. Re-inspecting its own output before returning is what makes
`residual` on the ScrubOutcome trustworthy rather than a guess (the PDF/
exiftool lesson from the integration plan: "exit 0" is not evidence of
removal).
"""

from __future__ import annotations

from reasoner.core.ports.watermark_port import ImageFormat, ImageInspectReport, ScrubOutcome
from reasoner.infrastructure.watermark.image.registry import module_for


class ImageMarkScrubber:
    """Default ImageMarkScrubberPort implementation, dispatching by format."""

    def supports(self, data: bytes) -> bool:
        return module_for(data) is not None

    def inspect(self, data: bytes) -> ImageInspectReport:
        module = module_for(data)
        if module is None:
            return ImageInspectReport(
                format=ImageFormat.UNKNOWN,
                has_c2pa=False,
                has_ai_metadata=False,
                notes=("unsupported or unrecognized image format",),
            )
        return module.inspect(data)

    def scrub(self, data: bytes, *, strip_all_metadata: bool = True) -> ScrubOutcome:
        module = module_for(data)
        if module is None:
            return ScrubOutcome(
                data=data,
                degraded=True,
                degraded_reason="unsupported or unrecognized image format; input returned unchanged",
            )
        try:
            cleaned, actions = module.strip(data, strip_all_metadata=strip_all_metadata)
        except ValueError as exc:
            return ScrubOutcome(
                data=data,
                degraded=True,
                degraded_reason=f"scrub failed, input returned unchanged: {exc}",
            )

        after = module.inspect(cleaned)
        residual = after.has_c2pa or after.has_ai_metadata
        return ScrubOutcome(
            data=cleaned,
            actions=tuple(actions),
            findings=after.findings,
            residual=residual,
        )


__all__ = ["ImageMarkScrubber"]
