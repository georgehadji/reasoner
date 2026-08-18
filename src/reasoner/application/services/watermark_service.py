"""Facade over text (Layer A) and image-metadata provenance scrubbing.

Application layer: orchestrates the domain (`domain.watermark`, pure) and
the infrastructure adapters bound behind `core/ports/watermark_port.py`. API
routes and pipeline flows should go through this service rather than
importing `domain.watermark` or the image scrubber directly, so policy
(`EgressPolicy`) and capability reporting stay in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reasoner.application.services.egress_policy import EgressPolicy
from reasoner.core.ports.watermark_port import (
    ImageFormat,
    ImageInspectReport,
    ImageMarkScrubberPort,
    PixelScrubberPort,
    ScrubOutcome,
)
from reasoner.domain.watermark import (
    ScrubResult,
    ScrubStats,
    TextInspectReport,
    inspect_text,
    scrub_text,
)


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """What this deployment can actually do — drives UI affordances.

    Never advertise a capability that is not bound: the frontend gates every
    provenance affordance on this report rather than assuming.
    """

    image_formats: tuple[ImageFormat, ...]
    pixel_backend_bound: bool
    layer_b_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_formats": [fmt.value for fmt in self.image_formats],
            "pixel_backend_bound": self.pixel_backend_bound,
            "layer_b_enabled": self.layer_b_enabled,
        }


# Formats infrastructure/watermark/image/registry.py dispatches to. Kept here
# rather than introspecting the registry so capabilities() has no import-time
# dependency on the image-strategy wiring.
_SUPPORTED_IMAGE_FORMATS: tuple[ImageFormat, ...] = (
    ImageFormat.PNG,
    ImageFormat.JPEG,
    ImageFormat.WEBP,
    ImageFormat.AVIF,
    ImageFormat.HEIC,
)


def _unscrubbed_text_result(text: str, report: TextInspectReport) -> ScrubResult:
    """A ScrubResult that reports what's present but changed nothing.

    Used when `EgressPolicy.layer_a` is off: still worth showing findings,
    but scrub_text() must not run — the report and the text must not imply a
    scrub happened.
    """
    length = len(text)
    return ScrubResult(
        text=text,
        report=report,
        stats=ScrubStats(input_length=length, output_length=length),
    )


class WatermarkService:
    """Application-layer facade — the only thing routes/flows should call."""

    def __init__(self, image_scrubber: ImageMarkScrubberPort, pixel: PixelScrubberPort) -> None:
        self._image_scrubber = image_scrubber
        self._pixel = pixel

    def inspect_text(self, text: str) -> TextInspectReport:
        """Read-only: what carriers are present. Never mutates."""
        return inspect_text(text)

    def scrub_text(self, text: str, policy: EgressPolicy) -> ScrubResult:
        """Layer A carrier removal, gated by `policy.layer_a`."""
        if not policy.layer_a:
            return _unscrubbed_text_result(text, inspect_text(text, policy.layer_a_options))
        return scrub_text(text, policy.layer_a_options)

    def inspect_image(self, data: bytes) -> ImageInspectReport:
        """Read-only: format + provenance findings. Never mutates."""
        return self._image_scrubber.inspect(data)

    def scrub_image(self, data: bytes, policy: EgressPolicy) -> ScrubOutcome:
        """Strip provenance metadata, gated by `policy.image_metadata`.

        When the policy disables image scrubbing, returns a passthrough
        outcome carrying the original bytes and `degraded=True` with a
        reason, per the "no silent no-op" invariant (§10.2) -- callers must
        not mistake an unscrubbed image for a scrubbed one.
        """
        if not policy.image_metadata:
            return ScrubOutcome(
                data=data,
                degraded=True,
                degraded_reason="image metadata scrubbing disabled by policy",
            )
        return self._image_scrubber.scrub(data)

    def capabilities(self) -> CapabilityReport:
        """Mirrors the reference repo's `/capabilities` -- what's actually bound.

        `layer_b_enabled` is hardcoded False regardless of the
        `WATERMARK_LAYER_B_ENABLED` setting: no rewriter is bound yet
        (Phase 6). Reporting the raw setting here would let a deployment
        advertise a capability that doesn't exist.
        """
        from reasoner.infrastructure.watermark.pixel.noop import NoopPixelScrubber

        return CapabilityReport(
            image_formats=_SUPPORTED_IMAGE_FORMATS,
            pixel_backend_bound=not isinstance(self._pixel, NoopPixelScrubber),
            layer_b_enabled=False,
        )


__all__ = ["CapabilityReport", "WatermarkService"]
