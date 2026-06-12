"""Image and document extraction utilities using vision-capable LLMs."""

from __future__ import annotations

import base64
import logging
from typing import Optional

from reasoner.infrastructure.llm.registry import build_provider

logger = logging.getLogger(__name__)

# Cheap vision model for image captioning — prioritizes cost-effectiveness
# Tiered fallback: Gemini Flash-Lite (cheapest) → GLM-4.6V → Gemini 2.5 Flash
_CAPTION_MODELS = ["gemini-flash", "glm-4-airx", "gemini-pro"]

# OCR-optimized models — free/cheap models that specialize in verbatim text extraction
_OCR_MODELS = ["qianfan-ocr-fast", "gemini-flash"]

# Cache to avoid re-describing the same image
_image_cache: dict[str, str] = {}


def _compute_image_hash(content: bytes) -> str:
    """Compute a simple hash for image deduplication."""
    import hashlib
    return hashlib.sha256(content).hexdigest()[:16]


def _encode_image_base64(content: bytes) -> str:
    """Encode image bytes to base64 data URI."""
    return base64.b64encode(content).decode("utf-8")


def _detect_mime_type(filename: str) -> str:
    """Detect image mime type from filename extension."""
    ext = filename.lower().split(".")[-1] if "." in filename else "png"
    return f"image/{ext.replace('jpg', 'jpeg').replace('webp', 'webp').replace('png', 'png')}"


async def describe_image(content: bytes, filename: str) -> str:
    """
    Describe an image using a cheap vision-capable model via OpenRouter.

    Args:
        content: Raw image bytes
        filename: Original filename (for mime type detection)

    Returns:
        Detailed text description of the image
    """
    image_hash = _compute_image_hash(content)
    if image_hash in _image_cache:
        return _image_cache[image_hash]

    mime_type = _detect_mime_type(filename)
    b64_data = _encode_image_base64(content)

    # Build the multimodal message payload
    # OpenRouter format: content as list of {type, text/image_url} dicts
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Describe this image in detail. Include any text visible in the image, "
                        "charts, diagrams, tables, and their meaning. Be thorough and factual."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                        "detail": "high",
                    },
                },
            ],
        }
    ]

    last_error: Optional[str] = None
    for model_id in _CAPTION_MODELS:
        try:
            provider = build_provider(model_id)
            # Use the provider's underlying async client
            response = await provider._client.chat.completions.create(
                model=provider.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=1024,
                temperature=0.3,
            )
            if not response.choices:
                logger.warning("Image captioning returned empty choices for %s", model_id)
                continue
            description = response.choices[0].message.content or "[No description returned]"
            _image_cache[image_hash] = description
            return description

        except Exception as e:
            last_error = f"{model_id}: {e}"
            logger.warning(f"Image captioning failed with {model_id}: {e}")
            continue

    logger.error(f"All caption models failed. Last error: {last_error}")
    return f"[Image description unavailable — all vision models failed. Last error: {last_error}]"


async def ocr_image(content: bytes, filename: str) -> str:
    """
    Extract verbatim text from an image using an OCR-optimized model via OpenRouter.

    Args:
        content: Raw image bytes
        filename: Original filename (for mime type detection)

    Returns:
        Extracted text content, preserving line breaks and formatting where possible
    """
    image_hash = _compute_image_hash(content)
    cache_key = f"ocr:{image_hash}"
    if cache_key in _image_cache:
        return _image_cache[cache_key]

    mime_type = _detect_mime_type(filename)
    b64_data = _encode_image_base64(content)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Extract all text from this image. Preserve line breaks and formatting. "
                        "Output only the extracted text, no commentary."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                        "detail": "high",
                    },
                },
            ],
        }
    ]

    last_error: Optional[str] = None
    for model_id in _OCR_MODELS:
        try:
            provider = build_provider(model_id)
            response = await provider._client.chat.completions.create(
                model=provider.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=2048,
                temperature=0.1,
            )
            if not response.choices:
                logger.warning("OCR returned empty choices for %s", model_id)
                continue
            text = response.choices[0].message.content or ""
            text = text.strip()
            _image_cache[cache_key] = text
            return text

        except Exception as e:
            last_error = f"{model_id}: {e}"
            logger.warning(f"OCR failed with {model_id}: {e}")
            continue

    logger.error(f"All OCR models failed. Last error: {last_error}")
    return f"[OCR unavailable — all models failed. Last error: {last_error}]"
