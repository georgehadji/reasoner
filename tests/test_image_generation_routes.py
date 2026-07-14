from __future__ import annotations

import pytest

from reasoner.api.routes import images
from reasoner.api.schemas import GenerateImageRequest


@pytest.mark.asyncio
async def test_generate_image_preview_only_returns_enhanced_prompt(monkeypatch):
    async def fake_enhance(prompt: str, api_key: str | None = None) -> str:
        assert prompt == "draw a fox"
        return "cinematic fox portrait"

    async def fail_generate(**kwargs):
        raise AssertionError("generate_images should not run during preview_only")

    monkeypatch.setattr(images, "enhance_image_prompt", fake_enhance)
    monkeypatch.setattr(images, "generate_images", fail_generate)

    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox", preview_only=True),
        user=None,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert result == {
        "success": True,
        "images": [],
        "enhanced_prompt": "cinematic fox portrait",
        "rewritten_prompt": None,
    }


@pytest.mark.asyncio
async def test_generate_image_endpoint_respects_enhance_flag(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_generate_images(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "images": [{"image_data": "data:image/png;base64,abc", "model_used": "gpt-5-image"}],
            "enhanced_prompt": kwargs["prompt"],
            "rewritten_prompt": None,
        }

    monkeypatch.setattr(images, "generate_images", fake_generate_images)

    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox", enhance=False),
        user=None,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert captured["enhance"] is False
    assert result["success"] is True
    assert result["images"][0]["model_used"] == "gpt-5-image"


@pytest.mark.asyncio
async def test_generate_image_endpoint_passes_reference_images(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_generate_images(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "images": [{"image_data": "data:image/png;base64,abc", "model_used": "gemini-pro-image"}],
            "enhanced_prompt": kwargs["prompt"],
            "rewritten_prompt": None,
        }

    monkeypatch.setattr(images, "generate_images", fake_generate_images)

    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(
            prompt="restyle this portrait",
            reference_images=["data:image/png;base64,abc123"],
        ),
        user=None,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert captured["reference_images"] == ["data:image/png;base64,abc123"]
    assert result["success"] is True
