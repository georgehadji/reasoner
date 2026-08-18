"""Magic-byte format detection for images (PNG/JPEG/WebP/AVIF/HEIC).

Infrastructure layer: pure byte-sniffing, no I/O beyond the bytes already in
memory. Detection logic ported from the researched
watermarks-remover project (image_meta.py / format_dispatch.py).
"""

from __future__ import annotations

import struct

from reasoner.core.ports.watermark_port import ImageFormat

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOI = b"\xff\xd8"
WEBP_RIFF = b"RIFF"
WEBP_SIG = b"WEBP"

_AVIF_BRANDS = (b"avif", b"avis", b"avio")
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1", b"heif")


def detect_format(data: bytes) -> ImageFormat:
    """Sniff *data*'s image format from its leading bytes."""
    if data.startswith(PNG_SIGNATURE):
        return ImageFormat.PNG
    if data.startswith(JPEG_SOI):
        return ImageFormat.JPEG
    if len(data) >= 12 and data[:4] == WEBP_RIFF and data[8:12] == WEBP_SIG:
        return ImageFormat.WEBP
    isobmff = _detect_isobmff_brand(data)
    if isobmff is not None:
        return isobmff
    return ImageFormat.UNKNOWN


def _detect_isobmff_brand(data: bytes) -> ImageFormat | None:
    """AVIF/HEIC share the ISOBMFF ftyp-box container; the brand disambiguates."""
    if len(data) < 12 or data[4:8] != b"ftyp":
        return None
    box_size = struct.unpack(">I", data[0:4])[0]
    end = min(box_size, len(data), 64) if box_size >= 8 else min(len(data), 64)
    header_chunk = data[8:end]
    if any(brand in header_chunk for brand in _AVIF_BRANDS):
        return ImageFormat.AVIF
    if any(brand in header_chunk for brand in _HEIC_BRANDS):
        return ImageFormat.HEIC
    return None


__all__ = ["detect_format", "PNG_SIGNATURE", "JPEG_SOI", "WEBP_RIFF", "WEBP_SIG"]
