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
from reasoner.api.run_admission import admit_flat_charge, close_flat_charge
from reasoner.api.schemas import GenerateImageRequest
from reasoner.core.constants_limits import IMAGE_PREVIEW_ESTIMATED_COST_USD
from reasoner.domain.saas import User
from reasoner.infrastructure.llm.image_generation import enhance_image_prompt, generate_images

logger = logging.getLogger(__name__)
router = APIRouter()


def _scrub_generated_images(images: list[dict]) -> list[dict]:
    """Strip C2PA/AI-provenance metadata from generated images.

    On by default (WATERMARK_IMAGE_STRIP_GENERATED=true) as of 2026-08-19,
    an explicit operator decision. Reasoner requesting an image from a
    provider and then removing the provenance that provider attached is a
    materially different posture from a user cleaning their own upload --
    see docs/plans/watermark-removal-integration.md Part X.3, whose
    recommendation this overrides. A scrub failure on any one image degrades
    to that image's original data, never blocks the response.
    """
    from reasoner.core.settings import settings

    if not settings.WATERMARK_IMAGE_STRIP_GENERATED:
        return images

    from reasoner.infrastructure.watermark import data_url as data_url_codec
    from reasoner.infrastructure.watermark.scrubber import ImageMarkScrubber

    scrubber = ImageMarkScrubber()
    cleaned: list[dict] = []
    for image in images:
        raw = image.get("image_data")
        if not isinstance(raw, str):
            cleaned.append(image)
            continue
        try:
            mime_type, decoded = data_url_codec.parse_data_url(raw)
            outcome = scrubber.scrub(decoded)
            if outcome.degraded:
                cleaned.append(image)
                continue
            cleaned.append(
                {**image, "image_data": data_url_codec.to_data_url(mime_type, outcome.data)}
            )
        except Exception as exc:
            logger.warning("Generated-image provenance scrub failed: %s", exc)
            cleaned.append(image)
    return cleaned


async def _auto_select_models(
    body: GenerateImageRequest, num_images: int
) -> tuple[list[str] | None, list[str] | None]:
    """Pick models from prompt intent + measured price. Never raises.

    Intent picks the capability family; price picks the tier. An explicitly
    passed preset still wins on the tier. Any failure returns (None, None) so
    generate_images() falls through to its static presets.
    """
    try:
        from reasoner.hypergate.models import SubAgentInput
        from reasoner.hypergate.sub_agents import ImageModelSelector
        from reasoner.infrastructure.llm.image_model_catalogue import select_models
        from reasoner.infrastructure.llm.registry import build_provider
        from reasoner.infrastructure.llm.router import ProviderRouter

        sub_router = ProviderRouter(primary=build_provider("qwen3.5-flash"), verbose=False)
        out = await ImageModelSelector().execute(
            SubAgentInput(problem=body.prompt, agent_name="image_model"), sub_router
        )
        if out.error:
            return None, None
        family = out.result.get("family", "general")
        # An explicit preset overrides the model's tier hint; the family still
        # comes from the prompt.
        if "preset" in body.model_fields_set:
            tier = "premium" if "premium" in body.preset else "budget"
        else:
            tier = out.result.get("tier_hint", "budget")
        primaries, fallbacks = select_models(
            family, tier, num_images, needs_reference_input=bool(body.reference_images)
        )
        logger.info("Auto image models: family=%s tier=%s → %s", family, tier, primaries)
        return primaries, fallbacks
    except Exception as exc:
        logger.warning("Automatic image model selection failed, using presets: %s", exc)
        return None, None


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

    if body.preview_only:
        # One LLM call: charged flat like any other paid call (BIL-26).
        charge = await admit_flat_charge(
            request, user=user, cost_usd=IMAGE_PREVIEW_ESTIMATED_COST_USD, kind="image-preview"
        )
        served = False
        try:
            enhanced_prompt = await enhance_image_prompt(body.prompt)
            served = True
            return {
                "success": True,
                "images": [],
                "enhanced_prompt": enhanced_prompt,
                "rewritten_prompt": None,
            }
        except Exception as exc:
            logger.error("Image generation endpoint error: %s", exc)
            return {"success": False, "error": "Internal server error"}
        finally:
            await close_flat_charge(charge, served=served)

    # The hold is the charge (not true-up'd against actual spend -- see the
    # module comment on estimate_service._IMAGE_COST_PER_IMAGE_USD). Given back
    # in full on any failure below, a client disconnect included.
    from reasoner.application.services.estimate_service import estimate_image_cost

    estimated_cost = await estimate_image_cost(body.preset, body.num_images)
    charge = await admit_flat_charge(request, user=user, cost_usd=estimated_cost, kind="image")

    served = False
    try:
        auto_primaries, auto_fallbacks = await _auto_select_models(body, body.num_images)
        result = await generate_images(
            prompt=body.prompt,
            preset=body.preset,
            enhance=body.enhance,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            reference_images=body.reference_images,
            num_images=body.num_images,
            model_aliases=auto_primaries,
            fallback_aliases=auto_fallbacks,
        )
        if not result.get("success"):
            logger.error("Image generation failed: %s", result.get("error"))
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
            }
        served = True
        return {
            "success": True,
            "images": _scrub_generated_images(result["images"]),
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
    finally:
        await close_flat_charge(charge, served=served)
