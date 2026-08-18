"""Provenance/watermark-scrubbing endpoints — inspect and remove AI-provenance
carriers from text (Layer A) and image metadata (C2PA/EXIF/XMP).

See docs/plans/watermark-removal-integration.md Part V.6 and Part X for the
capability boundaries and legal/ethical posture these routes must honor:
never claim more than what was verifiably removed, never advertise a
capability `WatermarkService.capabilities()` doesn't actually bind.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit, get_watermark_service
from reasoner.application.services.egress_policy import resolve_egress_policy
from reasoner.application.services.watermark_service import WatermarkService
from reasoner.infrastructure.uploader import MAX_FILE_SIZE
from reasoner.infrastructure.watermark import data_url as data_url_codec
from reasoner.infrastructure.watermark.data_url import DataUrlError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provenance", tags=["provenance"])

# Text inspect/scrub is O(length) over a fixed carrier alphabet -- generous,
# but not unbounded against an anonymous, rate-limited endpoint.
_MAX_CONTENT_CHARS = 500_000


class ProvenanceContentRequest(BaseModel):
    """At least one of `content`/`image` is required."""

    content: str | None = Field(None, max_length=_MAX_CONTENT_CHARS)
    image: str | None = Field(None, description="A data: URL, e.g. 'data:image/png;base64,...'")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _require_something(self) -> "ProvenanceContentRequest":
        if self.content is None and self.image is None:
            raise ValueError("At least one of 'content' or 'image' is required.")
        return self


class ProvenanceScrubRequest(ProvenanceContentRequest):
    layer_a: bool | None = None
    image_metadata: bool | None = None


def _decode_image(image: str) -> tuple[str, bytes]:
    try:
        mime_type, data = data_url_codec.parse_data_url(image)
    except DataUrlError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image data URL: {exc}") from exc
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    return mime_type, data


@router.get("/capabilities")
async def get_capabilities(
    service: WatermarkService = Depends(get_watermark_service),
):
    """Which formats/backends are actually bound. Drives UI affordances."""
    return service.capabilities().to_dict()


@router.post("/inspect")
async def inspect(
    body: ProvenanceContentRequest,
    csrf_checked=Depends(require_csrf),
    rate_limit_checked=Depends(check_rate_limit),
    service: WatermarkService = Depends(get_watermark_service),
):
    """Read-only: report what provenance carriers are present. No mutation."""
    result: dict = {}
    if body.content is not None:
        result["text"] = service.inspect_text(body.content).to_dict()
    if body.image is not None:
        _mime_type, data = _decode_image(body.image)
        result["image"] = service.inspect_image(data).to_dict()
    return result


@router.post("/scrub")
async def scrub(
    body: ProvenanceScrubRequest,
    csrf_checked=Depends(require_csrf),
    rate_limit_checked=Depends(check_rate_limit),
    service: WatermarkService = Depends(get_watermark_service),
):
    """Layer A text scrub and/or image-metadata scrub. Deterministic, cheap."""
    policy = resolve_egress_policy(layer_a=body.layer_a, image_metadata=body.image_metadata)
    result: dict = {}
    if body.content is not None:
        result["text"] = service.scrub_text(body.content, policy).to_dict()
    if body.image is not None:
        mime_type, data = _decode_image(body.image)
        outcome = service.scrub_image(data, policy)
        result["image"] = {
            **outcome.to_dict(),
            "image": data_url_codec.to_data_url(mime_type, outcome.data),
        }
    return result


@router.post("/rewrite")
async def rewrite(
    service: WatermarkService = Depends(get_watermark_service),
):
    """Layer B statistical rewrite -- not yet available.

    Ships behind `WATERMARK_LAYER_B_ENABLED` (default off) once Phase 6 binds
    a rewriter; until then this always reports unavailable rather than
    silently no-opping, per the "no silent no-op" invariant.
    """
    raise HTTPException(
        status_code=501,
        detail={
            "error": "Not implemented",
            "message": (
                "Statistical rewrite (Layer B) is not yet available in this deployment."
            ),
        },
    )


__all__ = ["router"]
