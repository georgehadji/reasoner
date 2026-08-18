"""Facade-level tests: registry dispatch, data-URL codec, ImageMarkScrubber,
and the Null Object pixel scrubber.

Format-specific scrubbing logic (PNG/JPEG/WebP/AVIF/HEIC) is already
thoroughly covered in tests/unit/test_watermark_image_{png,jpeg,webp,isobmff}.py
-- these tests verify dispatch and the bytes<->data-URL boundary, not
re-test format internals.
"""

from __future__ import annotations

import struct

import pytest

from reasoner.core.ports.watermark_port import ImageFormat, ImageMarkScrubberPort, PixelScrubberPort
from reasoner.infrastructure.watermark import data_url
from reasoner.infrastructure.watermark.image import registry
from reasoner.infrastructure.watermark.pixel.noop import NoopPixelScrubber
from reasoner.infrastructure.watermark.scrubber import ImageMarkScrubber

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(ctype: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", len(payload)) + ctype + payload + b"\x00\x00\x00\x00"


def _png(*extra_chunks: bytes) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + b"".join(extra_chunks)
        + _png_chunk(b"IDAT", b"\x00")
        + _png_chunk(b"IEND")
    )


CLEAN_PNG = _png()
C2PA_PNG = _png(_png_chunk(b"caBX", b"c2pa manifest"))


class TestRegistryDispatch:
    def test_png_dispatches_to_png_module(self):
        from reasoner.infrastructure.watermark.image import png as png_module

        assert registry.module_for(CLEAN_PNG) is png_module

    def test_unknown_bytes_dispatch_to_none(self):
        assert registry.module_for(b"not an image") is None

    def test_supported_formats_covers_all_five(self):
        formats = set(registry.supported_formats())
        assert formats == {
            ImageFormat.PNG,
            ImageFormat.JPEG,
            ImageFormat.WEBP,
            ImageFormat.AVIF,
            ImageFormat.HEIC,
        }


class TestDataUrlRoundTrip:
    def test_parse_then_reencode_round_trips(self):
        original = b"\x89PNG binary bytes here"
        url = data_url.to_data_url("image/png", original)
        mime, decoded = data_url.parse_data_url(url)
        assert mime == "image/png"
        assert decoded == original

    def test_parse_rejects_non_data_url(self):
        with pytest.raises(data_url.DataUrlError, match="not a data"):
            data_url.parse_data_url("https://example.com/image.png")

    def test_parse_rejects_non_base64_data_url(self):
        with pytest.raises(data_url.DataUrlError, match="base64"):
            data_url.parse_data_url("data:text/plain,hello")

    def test_parse_rejects_invalid_base64_payload(self):
        with pytest.raises(data_url.DataUrlError, match="invalid base64"):
            data_url.parse_data_url("data:image/png;base64,not-valid-base64!!!")

    def test_mime_for_format_known(self):
        assert data_url.mime_for_format(ImageFormat.PNG) == "image/png"
        assert data_url.mime_for_format(ImageFormat.WEBP) == "image/webp"

    def test_mime_for_format_unknown_falls_back(self):
        assert data_url.mime_for_format(ImageFormat.UNKNOWN) == "application/octet-stream"


class TestImageMarkScrubber:
    scrubber = ImageMarkScrubber()

    def test_supports_known_format(self):
        assert self.scrubber.supports(CLEAN_PNG) is True

    def test_supports_unknown_format(self):
        assert self.scrubber.supports(b"not an image") is False

    def test_inspect_delegates_to_format_module(self):
        report = self.scrubber.inspect(C2PA_PNG)
        assert report.has_c2pa is True

    def test_inspect_unsupported_format_reports_note(self):
        report = self.scrubber.inspect(b"not an image")
        assert report.format is ImageFormat.UNKNOWN
        assert report.notes

    def test_scrub_removes_c2pa_and_is_not_residual(self):
        outcome = self.scrubber.scrub(C2PA_PNG)
        assert outcome.residual is False
        assert outcome.degraded is False
        assert outcome.actions

    def test_scrub_unsupported_format_is_degraded(self):
        outcome = self.scrubber.scrub(b"not an image")
        assert outcome.degraded is True
        assert outcome.data == b"not an image"  # unchanged

    def test_scrub_malformed_known_format_is_degraded_not_raised(self):
        # A WebP-detected-but-truncated payload: strip() raises ValueError
        # internally; the facade must catch it, not propagate.
        truncated_webp = (
            b"RIFF" + struct.pack("<I", 20) + b"WEBP" + b"VP8X" + struct.pack("<I", 999) + b"short"
        )
        outcome = self.scrubber.scrub(truncated_webp)
        assert outcome.degraded is True
        assert outcome.data == truncated_webp


class TestPortConformance:
    def test_image_mark_scrubber_satisfies_port(self):
        assert isinstance(ImageMarkScrubber(), ImageMarkScrubberPort)

    def test_noop_pixel_scrubber_satisfies_port(self):
        assert isinstance(NoopPixelScrubber(), PixelScrubberPort)


class TestNoopPixelScrubber:
    @pytest.mark.asyncio
    async def test_always_unavailable(self):
        scrubber = NoopPixelScrubber()
        assert await scrubber.available() is False

    @pytest.mark.asyncio
    async def test_scrub_returns_degraded_outcome_unchanged(self):
        scrubber = NoopPixelScrubber()
        outcome = await scrubber.scrub(b"original bytes")
        assert outcome.degraded is True
        assert outcome.data == b"original bytes"
