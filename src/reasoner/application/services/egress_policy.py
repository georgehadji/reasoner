"""Resolve the effective watermark/provenance-scrubbing policy for a request.

Precedence: explicit request flag > `settings` default. Yields a frozen
`EgressPolicy` so a request's WatermarkService calls are always driven by one
consistent, already-resolved decision rather than re-reading `settings` at
each call site.
"""

from __future__ import annotations

from dataclasses import dataclass

from reasoner.core.settings import settings
from reasoner.domain.watermark import DEFAULT_OPTIONS, ScrubOptions


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    """What WatermarkService should do for one request."""

    layer_a: bool
    layer_a_options: ScrubOptions
    image_metadata: bool
    layer_b_enabled: bool


def resolve_egress_policy(
    *,
    layer_a: bool | None = None,
    image_metadata: bool | None = None,
    layer_a_options: ScrubOptions | None = None,
) -> EgressPolicy:
    """Build an `EgressPolicy`, letting an explicit request flag override settings.

    `None` means "no request-level opinion" -> fall back to the deployment
    default in `settings`. Layer B has no per-request opt-in yet (Phase 6);
    it always follows `settings.WATERMARK_LAYER_B_ENABLED`.
    """
    return EgressPolicy(
        layer_a=settings.WATERMARK_EGRESS_LAYER_A if layer_a is None else layer_a,
        layer_a_options=layer_a_options if layer_a_options is not None else DEFAULT_OPTIONS,
        image_metadata=(
            settings.WATERMARK_IMAGE_STRIP_UPLOADS if image_metadata is None else image_metadata
        ),
        layer_b_enabled=settings.WATERMARK_LAYER_B_ENABLED,
    )


__all__ = ["EgressPolicy", "resolve_egress_policy"]
