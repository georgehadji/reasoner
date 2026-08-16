"""Image generation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    require_auth_if_legacy_disabled,
)
from reasoner.api.schemas import GenerateImageRequest
from reasoner.domain.saas import User
from reasoner.infrastructure.llm.image_generation import enhance_image_prompt, generate_images

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/generate-image")
async def generate_image_endpoint(
    request: Request,
    body: GenerateImageRequest,
    user: User | None = Depends(require_auth_if_legacy_disabled),
    rate_limit_checked=Depends(check_rate_limit),
    csrf_checked=Depends(require_csrf),
    quota=Depends(check_quota_if_authenticated),
):
    """Generate images from a text prompt using 2 multimodal models in parallel.

    Automatically enhances the prompt before generation.

    Uses a 2-model parallel pair based on the selected preset:
      - budget: gemini-flash-image + gpt-5-image-mini
      - premium: gemini-pro-image + gpt-5-image
    """
    if quota is not None and not quota.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "message": quota.reason,
                "remaining": quota.remaining,
                "retry_after": quota.retry_after,
                "upgrade_url": "/pricing",
            },
            headers={
                "Retry-After": str(quota.retry_after or 3600),
                "X-RateLimit-Remaining": "0",
            },
        )

    try:
        if body.preview_only:
            enhanced_prompt = await enhance_image_prompt(body.prompt)
            return {
                "success": True,
                "images": [],
                "enhanced_prompt": enhanced_prompt,
                "rewritten_prompt": None,
            }
        result = await generate_images(
            prompt=body.prompt,
            preset=body.preset,
            enhance=body.enhance,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            reference_images=body.reference_images,
            num_images=body.num_images,
        )
        if not result.get("success"):
            logger.error("Image generation failed: %s", result.get("error"))
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
            }
        return {
            "success": True,
            "images": result["images"],
            "enhanced_prompt": result.get("enhanced_prompt"),
            "rewritten_prompt": result.get("rewritten_prompt"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Image generation endpoint error: %s", exc)
        return {
            "success": False,
            "error": "Internal server error",
        }
