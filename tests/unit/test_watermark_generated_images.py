"""_scrub_generated_images (api/routes/images.py): opt-in provenance strip
for AI-generated images, off by default (plan Part X.3).
"""

from __future__ import annotations

import struct

from reasoner.api.routes.images import _scrub_generated_images
from reasoner.core.settings import settings
from reasoner.infrastructure.watermark import data_url

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(ctype: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", len(payload)) + ctype + payload + b"\x00\x00\x00\x00"


def _c2pa_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"caBX", b"c2pa manifest bytes")
        + _png_chunk(b"IDAT", b"\x00")
        + _png_chunk(b"IEND")
    )


def _image_entry(png_bytes: bytes) -> dict:
    return {"image_data": data_url.to_data_url("image/png", png_bytes), "model_used": "fake-model"}


class TestOffByDefault:
    def test_disabled_returns_images_unchanged(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", False)
        images = [_image_entry(_c2pa_png())]
        result = _scrub_generated_images(images)
        assert result == images  # identical, not even re-encoded


class TestEnabledScrubsC2pa:
    def test_c2pa_removed_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        images = [_image_entry(_c2pa_png())]
        result = _scrub_generated_images(images)
        _mime, decoded = data_url.parse_data_url(result[0]["image_data"])
        assert b"c2pa manifest bytes" not in decoded
        assert b"caBX" not in decoded

    def test_model_used_preserved(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        images = [_image_entry(_c2pa_png())]
        result = _scrub_generated_images(images)
        assert result[0]["model_used"] == "fake-model"

    def test_clean_image_unaffected_content(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        clean_png = PNG_SIGNATURE + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ) + _png_chunk(b"IDAT", b"\x00") + _png_chunk(b"IEND")
        images = [_image_entry(clean_png)]
        result = _scrub_generated_images(images)
        _mime, decoded = data_url.parse_data_url(result[0]["image_data"])
        assert decoded == clean_png


class TestGracefulDegradation:
    def test_non_data_url_image_data_left_unchanged(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        images = [{"image_data": "https://example.com/not-a-data-url.png", "model_used": "x"}]
        result = _scrub_generated_images(images)
        assert result == images

    def test_missing_image_data_key_left_unchanged(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        images = [{"model_used": "x"}]
        result = _scrub_generated_images(images)
        assert result == images

    def test_unsupported_format_bytes_left_unchanged(self, monkeypatch):
        monkeypatch.setattr(settings, "WATERMARK_IMAGE_STRIP_GENERATED", True)
        raw_url = data_url.to_data_url("image/png", b"not actually a png")
        images = [{"image_data": raw_url, "model_used": "x"}]
        result = _scrub_generated_images(images)
        assert result[0]["image_data"] == raw_url  # degraded outcome -> original kept
