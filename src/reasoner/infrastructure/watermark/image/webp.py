"""WebP C2PA / AI-provenance metadata inspection and stripping.

Infrastructure layer: pure functions over bytes, no I/O. RIFF chunk-walk
logic ported from the researched watermarks-remover project (image_meta.py).

The VP8X feature-flag fixup below is the detail easiest to get wrong: after
dropping an ICCP/EXIF/XMP chunk, the corresponding bit in VP8X's flags byte
must also be cleared, or the rebuilt file declares metadata it no longer
carries and some decoders choke on the mismatch.
"""

from __future__ import annotations

import struct

from reasoner.core.ports.watermark_port import ImageFormat, ImageInspectReport, MarkFinding
from reasoner.domain.watermark.marks import MarkConfidence
from reasoner.infrastructure.watermark.image.detect import WEBP_RIFF, WEBP_SIG, detect_format
from reasoner.infrastructure.watermark.image.markers import (
    AI_META_HINTS,
    C2PA_MARKERS,
    contains_any,
    is_confirmed_c2pa_hit,
)

_METADATA_FLAG_BITS: dict[bytes, int] = {b"ICCP": 0x20, b"EXIF": 0x08, b"XMP ": 0x04}


def supports(data: bytes) -> bool:
    return detect_format(data) is ImageFormat.WEBP


def _walk_chunks(data: bytes) -> tuple[list[tuple[bytes, bytes, bytes]], tuple[str, ...]]:
    """Parse RIFF sub-chunks after the 12-byte RIFF/size/WEBP header.

    Returns (chunks, notes). Each chunk is (fourcc, payload, padding_bytes).
    Malformed/truncated input yields fewer chunks plus an explanatory note
    rather than raising -- callers decide whether that's fatal.
    """
    if not supports(data):
        return [], ("not a WebP",)

    notes: list[str] = []
    declared_size = struct.unpack("<I", data[4:8])[0]
    if declared_size + 8 != len(data):
        notes.append(f"RIFF size mismatch: header={declared_size + 8} actual={len(data)}")

    chunks: list[tuple[bytes, bytes, bytes]] = []
    pos = 12
    n = len(data)
    while pos + 8 <= n:
        fourcc = data[pos : pos + 4]
        length = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        payload_start = pos + 8
        payload_end = payload_start + length
        padded_end = payload_end + (length & 1)
        if padded_end > n:
            name = fourcc.decode("latin-1", errors="replace")
            notes.append(f"truncated WebP chunk {name}")
            break
        chunks.append((fourcc, data[payload_start:payload_end], data[payload_end:padded_end]))
        pos = padded_end
    else:
        if pos != n:
            notes.append(f"trailing WebP bytes: {n - pos}")

    return chunks, tuple(notes)


def inspect(data: bytes) -> ImageInspectReport:
    chunks, notes = _walk_chunks(data)
    if not chunks and notes == ("not a WebP",):
        return ImageInspectReport(format=ImageFormat.WEBP, has_c2pa=False, has_ai_metadata=False, notes=notes)

    findings: list[MarkFinding] = []
    has_c2pa = False
    has_ai = False
    for fourcc, payload, _padding in chunks:
        name = fourcc.decode("latin-1", errors="replace")
        if fourcc.upper() == b"C2PA":
            has_c2pa = True
            has_ai = True
            findings.append(MarkFinding("WebP C2PA chunk", MarkConfidence.CONFIRMED))
            continue
        if fourcc in (b"XMP ", b"EXIF"):
            hits = contains_any(payload, AI_META_HINTS + C2PA_MARKERS)
            if hits:
                has_ai = True
                if is_confirmed_c2pa_hit(hits):
                    has_c2pa = True
                findings.append(MarkFinding(f"WebP {name}: {', '.join(hits[:8])}", MarkConfidence.PROBABLE))

    return ImageInspectReport(
        format=ImageFormat.WEBP,
        has_c2pa=has_c2pa,
        has_ai_metadata=has_ai or has_c2pa,
        findings=tuple(findings),
        notes=notes,
    )


def strip(data: bytes, *, strip_all_metadata: bool = True) -> tuple[bytes, tuple[str, ...]]:
    chunks, notes = _walk_chunks(data)
    if not chunks and notes == ("not a WebP",):
        raise ValueError("not WebP")
    if notes:
        raise ValueError("malformed WebP: " + "; ".join(notes))

    actions: list[str] = []
    kept: list[tuple[bytes, bytes, bytes]] = []
    removed_flags = 0

    for fourcc, payload, padding in chunks:
        drop = fourcc.upper() == b"C2PA"
        if fourcc in _METADATA_FLAG_BITS:
            drop = strip_all_metadata or bool(contains_any(payload, AI_META_HINTS + C2PA_MARKERS))
        if drop:
            name = fourcc.decode("latin-1", errors="replace")
            actions.append(f"drop WebP chunk {name}")
            removed_flags |= _METADATA_FLAG_BITS.get(fourcc, 0)
        else:
            kept.append((fourcc, payload, padding))

    body = bytearray(WEBP_SIG)
    for fourcc, payload, padding in kept:
        if fourcc == b"VP8X" and len(payload) >= 1 and removed_flags:
            payload = bytes([payload[0] & ~removed_flags]) + payload[1:]
        body.extend(fourcc)
        body.extend(struct.pack("<I", len(payload)))
        body.extend(payload)
        body.extend(padding if len(payload) & 1 else b"")

    if not actions:
        actions.append("no WebP metadata chunks removed (already clean or none matched)")
    return WEBP_RIFF + struct.pack("<I", len(body)) + bytes(body), tuple(actions)


__all__ = ["supports", "inspect", "strip"]
