"""Image generation via OpenRouter multimodal API.

Supports:
  - Automatic prompt enhancement via a cheap text model
  - Parallel generation with 2 different image models
  - Graceful degradation if one model fails
"""

from __future__ import annotations

import asyncio
import base64
import copy
import logging
import os
import re
from typing import Any

import httpx
import openai

from reasoner.core.constants import (
    IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS,
    IMAGE_GEN_DEFAULT_ASPECT_RATIO,
    IMAGE_GEN_DEFAULT_HEIGHT,
    IMAGE_GEN_DEFAULT_RESOLUTION,
    IMAGE_GEN_DEFAULT_WIDTH,
    IMAGE_GEN_ENHANCEMENT_MODEL,
    IMAGE_GEN_ENHANCEMENT_SYSTEM_PROMPT,
    IMAGE_GEN_FALLBACKS,
    IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT,
    IMAGE_GEN_PRESETS,
    IMAGE_GEN_PROMPT_MAX_TOKENS,
    IMAGE_GEN_PROMPT_TEMPERATURE,
    IMAGE_GEN_REMOTE_TIMEOUT_SECONDS,
    OPENROUTER_BASE_URL,
)

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Raised when image generation fails after all fallbacks."""


_POLICY_ERROR_MARKERS = (
    "content policy",
    "policy violation",
    "request moderated",
    "moderated",
    "safety",
    "copyright",
    "trademark",
    "franchise",
    "disallowed",
    "not allowed",
    "refused",
)

_NON_IMAGE_RESPONSE_MARKERS = (
    "could not extract image",
    "no extractable image data or text",
    "no extractable image",
    "empty choices",
)

_POLICY_RISK_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmickey mouse\b", re.IGNORECASE), "an original cheerful cartoon mouse adventurer"),
    (re.compile(r"\bminnie mouse\b", re.IGNORECASE), "an original stylish cartoon mouse companion"),
    (re.compile(r"\bdonald duck\b", re.IGNORECASE), "an original spirited sailor duck"),
    (re.compile(r"\bdaisy duck\b", re.IGNORECASE), "an original elegant cartoon duck companion"),
    (re.compile(r"\bscrooge mcduck\b", re.IGNORECASE), "an original adventurous tycoon duck"),
    (re.compile(r"\buncle scrooge\b", re.IGNORECASE), "an original seasoned explorer duck"),
    (re.compile(r"\bfethry duck\b", re.IGNORECASE), "an original quirky inventor duck"),
    (re.compile(r"\bflintheart glomgold\b", re.IGNORECASE), "an original rival magnate duck"),
    (re.compile(r"\bmagica de spell\b", re.IGNORECASE), "an original arcane sorceress"),
    (re.compile(r"\bgyro gearloose\b", re.IGNORECASE), "an original eccentric engineer"),
    (re.compile(r"\bgrandma duck\b", re.IGNORECASE), "an original warm countryside caretaker duck"),
    (re.compile(r"\b(ducktales|duck tales)\b", re.IGNORECASE), "a classic adventurous cartoon duck ensemble"),
    (re.compile(r"\bduckburg\b", re.IGNORECASE), "a bustling original coastal city of adventurous ducks"),
    (re.compile(r"\bduck family\b", re.IGNORECASE), "an original family of adventurous ducks"),
    (re.compile(r"\bhuey\b", re.IGNORECASE), "an original intrepid duck sibling"),
    (re.compile(r"\bdewey\b", re.IGNORECASE), "an original curious duck sibling"),
    (re.compile(r"\blouie\b", re.IGNORECASE), "an original clever duck sibling"),
    (re.compile(r"\bmcduck\b", re.IGNORECASE), "an original explorer duck"),
    (re.compile(r"\bduck nephews\b", re.IGNORECASE), "an original trio of adventurous duck siblings"),
    (re.compile(r"\bgoofy\b", re.IGNORECASE), "an original lanky cartoon sidekick"),
    (re.compile(r"\bdisney(?:'s)?\b", re.IGNORECASE), "classic storybook animation"),
    (re.compile(r"\bpixar\b", re.IGNORECASE), "stylized cinematic animation"),
    (re.compile(r"\bdreamworks\b", re.IGNORECASE), "bold family-adventure animation"),
    (re.compile(r"\bmarvel\b", re.IGNORECASE), "original superhero adventure"),
    (re.compile(r"\bdc\b", re.IGNORECASE), "original comic-book heroics"),
    (re.compile(r"\bstar wars\b", re.IGNORECASE), "an original space-opera world"),
    (re.compile(r"\bpokemon\b", re.IGNORECASE), "original creature companions"),
    (re.compile(r"\bharry potter\b", re.IGNORECASE), "an original magical academy adventure"),
    (re.compile(r"\blord of the rings\b", re.IGNORECASE), "an original mythic fantasy realm"),
    (re.compile(r"\basterix\b", re.IGNORECASE), "an original witty Gaulish comic hero"),
)

_POLICY_RISK_TERMS: tuple[str, ...] = (
    "disney",
    "pixar",
    "dreamworks",
    "marvel",
    "star wars",
    "pokemon",
    "harry potter",
    "lord of the rings",
    "asterix",
    "mickey mouse",
    "minnie mouse",
    "donald duck",
    "daisy duck",
    "scrooge mcduck",
    "uncle scrooge",
    "fethry duck",
    "flintheart glomgold",
    "magica de spell",
    "gyro gearloose",
    "grandma duck",
    "ducktales",
    "duckburg",
    "duck family",
    "duck nephews",
    "huey",
    "dewey",
    "louie",
    "mcduck",
    "goofy",
)


def _looks_like_base64_image(value: str) -> bool:
    """Heuristic check for raw image base64 payloads."""
    cleaned = value.strip().strip('"').strip("'").strip("`").strip()
    if len(cleaned) < 500:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=\s]+", cleaned):
        return False
    compact = re.sub(r"\s+", "", cleaned)
    try:
        decoded = base64.b64decode(compact, validate=True)
    except Exception:
        return False
    # Common image signatures: PNG, JPEG, GIF, WEBP
    return decoded.startswith(
        (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")
    )


def _guess_image_mime(decoded: bytes) -> str:
    """Infer the MIME type from image bytes."""
    if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if decoded.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if decoded.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _normalize_image_data(value: str) -> str | None:
    """Normalize data URLs or raw base64 into a displayable data URL."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.startswith("data:image/"):
        return cleaned
    if _looks_like_base64_image(cleaned):
        compact = re.sub(r"\s+", "", cleaned)
        decoded = base64.b64decode(compact, validate=True)
        return f"data:{_guess_image_mime(decoded)};base64,{compact}"
    return None


def _normalize_explicit_base64_image(value: str) -> str | None:
    """Normalize base64 image payloads from explicit image fields such as b64_json."""
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", "", value.strip())
    if not cleaned:
        return None
    try:
        decoded = base64.b64decode(cleaned, validate=True)
    except Exception:
        return None
    if not decoded.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")):
        return None
    return f"data:{_guess_image_mime(decoded)};base64,{cleaned}"


def _extract_remote_urls_from_text(text: str) -> list[str]:
    """Extract remote URLs from freeform text, including markdown links."""
    if not text:
        return []
    matches = re.findall(r"https?://[^\s)>\]\"']+", text)
    return list(dict.fromkeys(match.rstrip(".,;") for match in matches))


def _looks_like_remote_image_url(value: str, *, allow_unhinted: bool = False) -> bool:
    """Best-effort check for a remote image URL."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    if allow_unhinted:
        return True
    return any(
        token in lowered
        for token in (".png", ".jpg", ".jpeg", ".gif", ".webp", "/image", "image=", "format=png", "format=jpeg", "format=jpg", "format=webp")
    )


def _image_bytes_to_data_url(content: bytes, content_type: str | None = None) -> str:
    """Convert image bytes into a data URL."""
    mime_type = content_type or _guess_image_mime(content)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _download_image_url(url: str, *, allow_unhinted: bool = False) -> str | None:
    """Fetch a remote image URL and convert it to a data URL."""
    if not _looks_like_remote_image_url(url, allow_unhinted=allow_unhinted):
        return None

    from reasoner.security.url_validator import is_safe_url
    if not is_safe_url(url):
        logger.warning("Blocked unsafe image URL: %s", url)
        return None

    try:
        async with httpx.AsyncClient(timeout=IMAGE_GEN_REMOTE_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to download generated image URL %s: %s", url, exc)
        return None

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    content = response.content
    if not content:
        return None
    if content_type and not content_type.startswith("image/") and not content.startswith(
        (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")
    ):
        return None

    normalized_type = content_type if content_type.startswith("image/") else None
    return _image_bytes_to_data_url(content, normalized_type)


def _extract_base64_from_text(text: str) -> str | None:
    """Extract base64 image data from text, handling markdown and code blocks."""
    if not text:
        return None

    # Try to find data:image URL first (most reliable)
    m = re.search(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}", text)
    if m:
        return m.group(0)

    # Preprocess text to remove common delimiters
    # Remove markdown code blocks: ```language\ncontent\n```
    text = re.sub(r"```[a-z]*\n", "\n", text)
    text = re.sub(r"\n```", "\n", text)
    # Remove inline code backticks, keep content
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove other common wrappers: [], (), {}, <>
    text = re.sub(r"[\[\](){}<>]", " ", text)
    # Remove quotes
    text = re.sub(r"['\"]", "", text)

    # Find all potential base64 sequences
    # Base64 alphabet: A-Z, a-z, 0-9, +, /, =, and whitespace
    pattern = r"[A-Za-z0-9+/=\s]{500,}"
    matches = re.findall(pattern, text)
    if matches:
        # Return the longest match (most likely to be image data)
        longest = max(matches, key=len)
        # Normalize it
        normalized = _normalize_image_data(longest)
        if normalized:
            return normalized

    # Last resort: look for any base64 string > 100 chars (might be incomplete)
    pattern2 = r"[A-Za-z0-9+/=\s]{100,}"
    matches = re.findall(pattern2, text)
    if matches:
        longest = max(matches, key=len)
        normalized = _normalize_image_data(longest)
        if normalized and _looks_like_base64_image(longest):
            return normalized

    return None


def _extract_text_from_content_parts(content: Any) -> str:
    """Best-effort extraction of text from string or structured content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    nested = text.get("value")
                    if isinstance(nested, str):
                        parts.append(nested)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                elif text is not None:
                    nested = getattr(text, "value", None)
                    if isinstance(nested, str):
                        parts.append(nested)
        return "\n".join(part for part in parts if part)
    return ""


def _collect_image_candidates(node: Any) -> tuple[list[str], list[str]]:
    """Recursively search a response/message payload for inline image data or remote URLs."""
    inline_candidates: list[str] = []
    remote_candidates: list[str] = []
    seen: set[int] = set()

    def visit(value: Any) -> None:
        obj_id = id(value)
        if obj_id in seen:
            return
        seen.add(obj_id)

        if value is None:
            return
        if isinstance(value, str):
            normalized = _normalize_image_data(value)
            if normalized:
                inline_candidates.append(normalized)
                return
            match = re.search(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}", value)
            if match:
                inline_candidates.append(match.group(0))
                return
            if _looks_like_remote_image_url(value):
                remote_candidates.append(value.strip())
            for url in _extract_remote_urls_from_text(value):
                remote_candidates.append(url)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"b64_json", "base64"} and isinstance(item, str):
                    normalized = _normalize_explicit_base64_image(item)
                    if normalized:
                        inline_candidates.append(normalized)
                        continue
                if key in {"url", "image_url", "source"} and isinstance(item, str) and _looks_like_remote_image_url(item, allow_unhinted=True):
                    remote_candidates.append(item.strip())
                    continue
                visit(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        object_dict = getattr(value, "__dict__", None)
        if isinstance(object_dict, dict):
            for attr in ("url", "image_url", "data", "b64_json", "base64", "content", "image", "source", "images"):
                if attr in object_dict:
                    visit(object_dict[attr])

    visit(node)
    # Preserve order while deduplicating.
    return list(dict.fromkeys(inline_candidates)), list(dict.fromkeys(remote_candidates))


async def _resolve_first_image_candidate(node: Any) -> str | None:
    """Return the first usable image candidate from a response payload."""
    inline_candidates, remote_candidates = _collect_image_candidates(node)
    if inline_candidates:
        return inline_candidates[0]

    for candidate in remote_candidates:
        downloaded = await _download_image_url(candidate, allow_unhinted=True)
        if downloaded:
            return downloaded

    return None


def _resolve_model_config(alias: str) -> dict[str, Any]:
    """Resolve a model alias to its full registry configuration."""
    from reasoner.infrastructure.llm.registry import _REGISTRY

    if alias not in _REGISTRY:
        raise ValueError(f"Unknown image generation model alias: {alias}")
    return _REGISTRY[alias]


def _get_modalities(model_id: str) -> list[str] | None:
    """Determine modalities for the model. Returns None if not applicable."""
    lowered = model_id.lower()
    if "gemini" in lowered:
        return ["text", "image"]
    if "gpt-" in lowered and "image" in lowered:
        return ["text", "image"]
    # For some models, modalities might not be strictly supported yet by standard OpenAI SDK
    # or might be better handled by skipping it and letting the model default.
    return ["image"]


def _should_prefer_images_api(model_id: str) -> bool:
    """Use the dedicated images API first for image-native models."""
    lowered = model_id.lower()
    return any(token in lowered for token in ("image", "flux", "seedream", "riverflow", "recraft"))


async def _enhance_image_prompt(user_prompt: str, api_key: str | None = None) -> str:
    """Enhance a simple image prompt into a detailed one.

    Returns the enhanced prompt, or the original on failure.
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        logger.warning("No API key for prompt enhancement; using raw prompt")
        return user_prompt

    try:
        from reasoner.infrastructure.llm.registry import build_provider

        provider = build_provider(IMAGE_GEN_ENHANCEMENT_MODEL)
        enhanced = await provider.complete(
            system_prompt=IMAGE_GEN_ENHANCEMENT_SYSTEM_PROMPT,
            user_prompt=f"Original description: {user_prompt}",
            max_tokens=IMAGE_GEN_PROMPT_MAX_TOKENS,
            temperature=IMAGE_GEN_PROMPT_TEMPERATURE,
        )
        enhanced = enhanced.strip().strip('"').strip("'")
        if enhanced:
            logger.info("Prompt enhanced: %r -> %r", user_prompt[:60], enhanced[:60])
            return enhanced
    except Exception as exc:
        logger.warning("Prompt enhancement failed: %s", exc)

    return user_prompt


async def enhance_image_prompt(user_prompt: str, api_key: str | None = None) -> str:
    """Public wrapper for image-prompt enhancement used by API preflight flows."""
    return await _enhance_image_prompt(user_prompt, api_key=api_key)


def _contains_policy_risk_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _POLICY_RISK_TERMS)


def _heuristic_policy_safe_rewrite(prompt: str) -> str | None:
    """Best-effort local rewrite when the model-based policy rewrite fails."""
    if not prompt:
        return None

    rewritten = prompt
    for pattern, replacement in _POLICY_RISK_REPLACEMENTS:
        rewritten = pattern.sub(replacement, rewritten)

    rewritten = re.sub(
        r"\b(?:in the style of|styled like|inspired by|evoking|channeling)\s+[^,.;:]+",
        "in a polished original visual style",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"\b(featuring|with|starring|including|depicting)\s+([A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,4}(?:\s*(?:,|and|&)\s*[A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,4})*)",
        r"\1 an original ensemble of expressive characters",
        rewritten,
    )
    rewritten = re.sub(r"\s{2,}", " ", rewritten)
    rewritten = re.sub(r"\s+([,.;:])", r"\1", rewritten).strip(" ,.;:")

    if not rewritten or rewritten == prompt or _contains_policy_risk_terms(rewritten):
        return None

    if "original" not in rewritten.lower():
        rewritten = (
            "Create an original, non-infringing scene with distinct characters and designs. "
            + rewritten
        )

    return rewritten


async def _rewrite_prompt_for_policy_safety(user_prompt: str, api_key: str | None = None) -> str | None:
    """Rewrite a prompt into an original non-infringing variant for safer image generation."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        try:
            from reasoner.infrastructure.llm.registry import build_provider

            provider = build_provider(IMAGE_GEN_ENHANCEMENT_MODEL)
            rewritten = await provider.complete(
                system_prompt=IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT,
                user_prompt=f"Rewrite this image prompt safely while preserving the scene intent: {user_prompt}",
                max_tokens=512,
                temperature=0.3,
            )
            rewritten = rewritten.strip().strip('"').strip("'")
            if rewritten:
                sanitized = _heuristic_policy_safe_rewrite(rewritten) or rewritten
                if sanitized and sanitized != user_prompt and not _contains_policy_risk_terms(sanitized):
                    logger.info("Policy-safe prompt rewrite generated: %r -> %r", user_prompt[:80], sanitized[:80])
                    return sanitized
        except Exception as exc:
            logger.warning("Policy-safe prompt rewrite failed: %s", exc)

    heuristic_rewrite = _heuristic_policy_safe_rewrite(user_prompt)
    if heuristic_rewrite:
        logger.info("Using heuristic policy-safe prompt rewrite: %r -> %r", user_prompt[:80], heuristic_rewrite[:80])
        return heuristic_rewrite

    return None


def _error_matches_any(error: str, markers: tuple[str, ...]) -> bool:
    lowered = error.lower()
    return any(marker in lowered for marker in markers)


def _should_retry_with_policy_safe_prompt(errors: list[str]) -> bool:
    """Retry when providers were moderated or produced text-only/non-image responses."""
    if not errors:
        return False
    saw_policy_block = any(_error_matches_any(error, _POLICY_ERROR_MARKERS) for error in errors)
    saw_non_image_response = any(_error_matches_any(error, _NON_IMAGE_RESPONSE_MARKERS) for error in errors)
    return saw_policy_block or (saw_non_image_response and len(errors) >= 2)


async def _run_generation_attempts(
    prompt: str,
    model_aliases: list[str],
    fallback_aliases: list[str],
    api_key: str | None,
    aspect_ratio: str,
    resolution: str,
    required_image_count: int = 2,
    reference_images: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Run primary and fallback models until the required image count is met or exhausted."""
    attempted_aliases = list(model_aliases)
    tasks = [
        asyncio.create_task(
            _generate_image_guarded(
                prompt,
                alias,
                api_key,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                reference_images=reference_images,
            ),
            name=alias,
        )
        for alias in model_aliases
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    images: list[dict[str, str]] = []
    errors: list[str] = []
    for alias, result in zip(model_aliases, results):
        if isinstance(result, Exception):
            msg = str(result)
            logger.warning("Image generation failed with %s: %s", alias, msg)
            errors.append(f"{alias}: {msg}")
        elif result.get("success"):
            images.append({
                "image_data": result["image_data"],
                "model_used": result["model_used"],
            })
        else:
            errors.append(f"{alias}: {result.get('error', 'unknown')}")

    if len(images) < required_image_count:
        for alias in fallback_aliases:
            if len(images) >= required_image_count:
                break
            if alias in attempted_aliases:
                continue
            attempted_aliases.append(alias)
            result = await _generate_image_guarded(
                prompt,
                alias,
                api_key,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                reference_images=reference_images,
            )
            if result.get("success"):
                images.append({
                    "image_data": result["image_data"],
                    "model_used": result["model_used"],
                })
                continue
            errors.append(f"{alias}: {result.get('error', 'unknown')}")

    return images[:required_image_count], errors


async def _generate_image_with_images_api(
    client: Any,
    model_id: str,
    prompt: str,
    extra_body: dict[str, Any],
    resolution: str,
    reference_images: list[str] | None = None,
) -> str | None:
    """Fallback to the dedicated images API when chat completions returns no image."""
    if reference_images:
        return None
    # OpenRouter does not support the /images/generations endpoint;
    # image generation works through chat.completions.create instead.
    base_url = str(getattr(client, "base_url", "") or "")
    if "openrouter.ai" in base_url:
        return None
    kwargs: dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "extra_body": extra_body,
    }
    if resolution:
        kwargs["size"] = resolution

    try:
        response = await asyncio.wait_for(
            client.images.generate(**kwargs),
            timeout=IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Images API fallback failed for %s: %s", model_id, exc)
        return None

    image_candidate = await _resolve_first_image_candidate(getattr(response, "data", None))
    if not image_candidate:
        try:
            dumped = response.model_dump()
        except Exception:
            dumped = None
        if dumped:
            image_candidate = await _resolve_first_image_candidate(dumped)

    return image_candidate


async def generate_image_with_model(
    prompt: str,
    model_alias: str,
    api_key: str | None = None,
    max_tokens: int = 2048,
    aspect_ratio: str = IMAGE_GEN_DEFAULT_ASPECT_RATIO,
    resolution: str = IMAGE_GEN_DEFAULT_RESOLUTION,
    reference_images: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a single image with a specific model alias.

    Returns:
        {"success": True, "image_data": "data:image/png;base64,...", "model_used": str}
    Raises:
        ImageGenerationError on failure.
    """
    cfg = _resolve_model_config(model_alias)
    model_id = cfg["model"]
    # Create a deep copy to avoid mutating the registry
    extra_body = copy.deepcopy(cfg.get("extra_body", {}))
    
    # Inject image_config for aspect ratio and resolution
    width, height = IMAGE_GEN_DEFAULT_WIDTH, IMAGE_GEN_DEFAULT_HEIGHT
    if "x" in resolution:
        try:
            w_s, h_s = resolution.split("x")
            width, height = int(w_s), int(h_s)
        except ValueError:
            pass

    image_config = {
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height
    }
    
    # Merge into extra_body
    if "image_config" in extra_body:
        extra_body["image_config"].update(image_config)
    else:
        extra_body["image_config"] = image_config

    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ImageGenerationError("OPENROUTER_API_KEY is not set")

    client = openai.AsyncOpenAI(
        api_key=key,
        base_url=OPENROUTER_BASE_URL,
    )

    modalities = _get_modalities(model_id)

    if _should_prefer_images_api(model_id) and not reference_images and "openrouter.ai" not in str(client.base_url or ""):
        image_candidate = await _generate_image_with_images_api(
            client,
            model_id,
            prompt,
            extra_body,
            resolution,
            reference_images=reference_images,
        )
        if image_candidate:
            return {
                "success": True,
                "image_data": image_candidate,
                "model_used": model_alias,
            }

    try:
        # Use kwargs for flexibility (handles older SDKs that don't know 'modalities')
        # For image generation models, use the content array format which is more reliable
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": [{
                "role": "user",
                "content": (
                    [{"type": "text", "text": prompt}]
                    + [
                        {"type": "image_url", "image_url": {"url": image_url}}
                        for image_url in (reference_images or [])
                    ]
                ),
            }],
            "max_tokens": max_tokens,
            "extra_body": extra_body,
        }
        if modalities:
            kwargs["modalities"] = modalities

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS,
            )
        except TypeError as exc:
            # Fallback for older OpenAI SDK versions (< 1.51.0)
            if "modalities" in str(exc):
                logger.warning("OpenAI SDK does not support 'modalities' argument; retrying without it.")
                kwargs.pop("modalities", None)
                response = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS,
                )
            else:
                raise
    except Exception as exc:
        raise ImageGenerationError(f"API call failed for {model_alias}: {exc}") from exc

    if not response.choices:
        image_candidate = await _generate_image_with_images_api(
            client,
            model_id,
            prompt,
            extra_body,
            resolution,
            reference_images=reference_images,
        )
        if image_candidate:
            return {
                "success": True,
                "image_data": image_candidate,
                "model_used": model_alias,
            }
        raise ImageGenerationError(f"Empty choices from {model_alias}")

    message = response.choices[0].message
    images = getattr(message, "images", None)
    image_candidate = await _resolve_first_image_candidate(images)
    if not image_candidate:
        image_candidate = await _resolve_first_image_candidate(getattr(message, "content", None))
    if not image_candidate:
        try:
            dumped = response.model_dump()
        except Exception:
            dumped = None
        if dumped:
            image_candidate = await _resolve_first_image_candidate(dumped)


    if image_candidate:
        return {
            "success": True,
            "image_data": image_candidate,
            "model_used": model_alias,
        }

    image_candidate = await _generate_image_with_images_api(
        client,
        model_id,
        prompt,
        extra_body,
        resolution,
        reference_images=reference_images,
    )
    if image_candidate:
        return {
            "success": True,
            "image_data": image_candidate,
            "model_used": model_alias,
        }

    # ── Text fallback for diagnostics ──
    content = getattr(message, "content", None)
    content_text = _extract_text_from_content_parts(content)
    if not content_text and not images:
        raise ImageGenerationError(f"No extractable image data or text from {model_alias}")

    # Search diagnostic text one last time in case content parts were flattened.
    extracted = _extract_base64_from_text(content_text)
    if extracted:
        return {
            "success": True,
            "image_data": extracted,
            "model_used": model_alias,
        }

    raise ImageGenerationError(
        f"Could not extract image from {model_alias} response. Content preview: {content_text[:100]}..."
    )


async def generate_images(
    prompt: str,
    preset: str = "budget",
    api_key: str | None = None,
    enhance: bool = True,
    aspect_ratio: str = IMAGE_GEN_DEFAULT_ASPECT_RATIO,
    resolution: str = IMAGE_GEN_DEFAULT_RESOLUTION,
    reference_images: list[str] | None = None,
    num_images: int = 2,
) -> dict[str, Any]:
    """Generate images in parallel with 2 models + optional prompt enhancement.

    Args:
        prompt: Text description of the desired image.
        preset: "budget" or "premium" — determines the 2-model pair.
        api_key: Optional OpenRouter API key.
        enhance: Whether to auto-enhance the prompt before generation.
        aspect_ratio: Requested aspect ratio (e.g. "1:1", "16:9").
        resolution: Requested resolution (e.g. "1024x1024").

    Returns:
        {
            "success": bool,
            "enhanced_prompt": str | None,
            "rewritten_prompt": str | None,
            "images": list[{"image_data": str, "model_used": str}],
            "error": str | None,
        }
    """
    tier = preset if preset in IMAGE_GEN_PRESETS else "budget"
    # When reference images are provided we need multimodal models that accept
    # image input (Flux/Riverflow are text-to-image only).
    if reference_images:
        if tier in ("budget", IMAGE_GEN_BUDGET_PRESET):
            model_aliases = ["gemini-flash-image", "gpt-5-image-mini"]
            fallback_aliases = ["gemini-3.1-flash-image-preview", "gemini-pro-image"]
        else:
            model_aliases = ["gemini-pro-image", "gpt-5-image"]
            fallback_aliases = ["gemini-3.1-flash-image-preview", "gemini-flash-image"]
    else:
        model_aliases = IMAGE_GEN_PRESETS[tier]
        fallback_aliases = IMAGE_GEN_FALLBACKS.get(tier, [])
    required_image_count = num_images

    # 1. Optional prompt enhancement
    final_prompt = prompt
    enhanced_prompt: str | None = None
    if enhance:
        final_prompt = await _enhance_image_prompt(prompt, api_key=api_key)
        if final_prompt != prompt:
            enhanced_prompt = final_prompt

    images, errors = await _run_generation_attempts(
        final_prompt,
        model_aliases,
        fallback_aliases,
        api_key,
        aspect_ratio,
        resolution,
        required_image_count=required_image_count,
        reference_images=reference_images,
    )

    rewritten_prompt: str | None = None
    if len(images) < required_image_count and _should_retry_with_policy_safe_prompt(errors):
        rewritten_prompt = await _rewrite_prompt_for_policy_safety(final_prompt, api_key=api_key)
        if rewritten_prompt and rewritten_prompt != final_prompt:
            logger.info("Retrying image generation with policy-safe rewritten prompt.")
            retry_images, retry_errors = await _run_generation_attempts(
                rewritten_prompt,
                model_aliases,
                fallback_aliases,
                api_key,
                aspect_ratio,
                resolution,
                required_image_count=required_image_count,
                reference_images=reference_images,
            )
            if len(retry_images) >= len(images):
                images = retry_images
            errors.extend(f"policy-retry::{error}" for error in retry_errors)

    # Last-resort hard sanitization retry if still short on images
    if len(images) < required_image_count:
        hard_sanitized = _heuristic_policy_safe_rewrite(final_prompt)
        tried_prompts = {final_prompt, rewritten_prompt} if rewritten_prompt else {final_prompt}
        if hard_sanitized and hard_sanitized not in tried_prompts:
            logger.info("Retrying image generation with hard-sanitized prompt fallback.")
            retry_images, retry_errors = await _run_generation_attempts(
                hard_sanitized,
                model_aliases,
                fallback_aliases,
                api_key,
                aspect_ratio,
                resolution,
                required_image_count=required_image_count,
                reference_images=reference_images,
            )
            if len(retry_images) >= len(images):
                images = retry_images
            errors.extend(f"hard-sanitize-retry::{error}" for error in retry_errors)

    if len(images) < required_image_count:
        if images:
            errors.append(
                f"Generated only {len(images)} of {required_image_count} required images"
            )
        return {
            "success": False,
            "enhanced_prompt": enhanced_prompt,
            "rewritten_prompt": rewritten_prompt,
            "images": [],
            "error": "All models failed. " + "; ".join(errors),
        }

    return {
        "success": True,
        "enhanced_prompt": enhanced_prompt,
        "rewritten_prompt": rewritten_prompt,
        "images": images,
        "error": None,
    }


async def _generate_image_guarded(
    prompt: str, 
    model_alias: str, 
    api_key: str | None,
    aspect_ratio: str = IMAGE_GEN_DEFAULT_ASPECT_RATIO,
    resolution: str = IMAGE_GEN_DEFAULT_RESOLUTION,
    reference_images: list[str] | None = None,
) -> dict[str, Any]:
    """Wrapper that catches exceptions and returns a dict."""
    try:
        return await generate_image_with_model(
            prompt, 
            model_alias, 
            api_key=api_key,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_images=reference_images,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}
