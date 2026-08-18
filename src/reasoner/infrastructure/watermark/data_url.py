"""Data-URL <-> bytes codec.

The adapter boundary between Reasoner's in-memory image representation
(data URLs) and the byte-oriented domain/port layer (ADR-3: bytes in, bytes
out — the domain and ports never see base64).
"""

from __future__ import annotations

import base64
import binascii
import re

from reasoner.core.ports.watermark_port import ImageFormat

_DATA_URL_RE = re.compile(r"^data:([^;,]+)(;base64)?,(.*)$", re.DOTALL)

_MIME_BY_FORMAT: dict[ImageFormat, str] = {
    ImageFormat.PNG: "image/png",
    ImageFormat.JPEG: "image/jpeg",
    ImageFormat.WEBP: "image/webp",
    ImageFormat.AVIF: "image/avif",
    ImageFormat.HEIC: "image/heic",
}


class DataUrlError(ValueError):
    """A string is not a well-formed, base64-encoded data: URL."""


def parse_data_url(data_url: str) -> tuple[str, bytes]:
    """Return (mime_type, decoded_bytes) from a data: URL.

    Raises DataUrlError for anything that isn't a recognizable, base64
    data: URL — callers should treat that as "not an image we can process",
    not crash.
    """
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise DataUrlError("not a data: URL")
    mime_type, is_base64, payload = match.groups()
    if not is_base64:
        raise DataUrlError("data: URL is not base64-encoded")
    try:
        return mime_type, base64.b64decode(payload, validate=True)
    except binascii.Error as exc:
        raise DataUrlError(f"invalid base64 payload: {exc}") from exc


def to_data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def mime_for_format(fmt: ImageFormat) -> str:
    """Best-effort MIME type for a detected format; falls back to a generic type."""
    return _MIME_BY_FORMAT.get(fmt, "application/octet-stream")


__all__ = ["DataUrlError", "parse_data_url", "to_data_url", "mime_for_format"]
