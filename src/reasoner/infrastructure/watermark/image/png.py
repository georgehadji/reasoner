"""PNG C2PA / AI-provenance metadata inspection and stripping.

Infrastructure layer: pure functions over bytes, no I/O. Chunk-walk logic
ported from the researched watermarks-remover project (image_meta.py).
CRC32 trailers are treated as opaque and copied through verbatim -- this
scrubber only inspects/rewrites chunk type, length, and payload.
"""

from __future__ import annotations

import struct

from reasoner.core.ports.watermark_port import ImageFormat, ImageInspectReport, MarkFinding
from reasoner.domain.watermark.marks import MarkConfidence
from reasoner.infrastructure.watermark.image.detect import PNG_SIGNATURE
from reasoner.infrastructure.watermark.image.markers import (
    AI_META_HINTS,
    C2PA_MARKERS,
    contains_any,
    is_confirmed_c2pa_hit,
)

# Private/ancillary chunks sometimes used for JUMBF/C2PA containers.
_C2PA_CHUNK_TYPES = (b"caBX", b"juMB", b"jumb")
_TEXT_CHUNK_TYPES = (b"tEXt", b"zTXt", b"iTXt", b"eXIf")


def supports(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE)


def inspect(data: bytes) -> ImageInspectReport:
    if not supports(data):
        return ImageInspectReport(
            format=ImageFormat.PNG,
            has_c2pa=False,
            has_ai_metadata=False,
            notes=("not a PNG",),
        )

    findings: list[MarkFinding] = []
    has_c2pa = False
    has_ai = False
    truncated = False

    pos = 8
    n = len(data)
    while pos + 8 <= n:
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk_start = pos + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > n:
            findings.append(
                MarkFinding(f"truncated chunk {ctype!r}", MarkConfidence.INFORMATIONAL)
            )
            truncated = True
            break
        payload = data[chunk_start:chunk_end]
        name = ctype.decode("latin-1", errors="replace")

        if ctype in _C2PA_CHUNK_TYPES or ctype.startswith(b"c2"):
            has_c2pa = True
            findings.append(
                MarkFinding(f"PNG chunk {name} (possible C2PA container)", MarkConfidence.CONFIRMED)
            )
        if ctype in _TEXT_CHUNK_TYPES:
            hits = contains_any(payload, AI_META_HINTS + C2PA_MARKERS)
            if hits:
                has_ai = True
                if is_confirmed_c2pa_hit(hits):
                    has_c2pa = True
                findings.append(
                    MarkFinding(f"PNG {name}: {', '.join(hits[:8])}", MarkConfidence.PROBABLE)
                )
        if ctype == b"IEND":
            break
        pos = chunk_end + 4

    whole = contains_any(data, C2PA_MARKERS)
    if whole and not has_c2pa:
        has_c2pa = True
        findings.append(
            MarkFinding(
                f"byte-scan C2PA markers: {', '.join(whole[:6])}",
                MarkConfidence.LIKELY_FALSE_POSITIVE,
            )
        )

    notes = (
        ("PNG parsing stopped at a truncated chunk; findings reflect only the parsed prefix.",)
        if truncated
        else ()
    )
    return ImageInspectReport(
        format=ImageFormat.PNG,
        has_c2pa=has_c2pa,
        has_ai_metadata=has_ai or has_c2pa,
        findings=tuple(findings),
        notes=notes,
    )


def strip(data: bytes, *, strip_all_metadata: bool = True) -> tuple[bytes, tuple[str, ...]]:
    """Drop C2PA/JUMBF chunks and AI-marked (or, by default, all) text chunks."""
    if not supports(data):
        raise ValueError("not a PNG")

    actions: list[str] = []
    out = bytearray(PNG_SIGNATURE)
    pos = 8
    n = len(data)
    while pos + 8 <= n:
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk_start = pos + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > n:
            actions.append(f"truncated chunk at offset {pos}; copied remainder verbatim")
            out.extend(data[pos:])
            return bytes(out), tuple(actions)
        payload = data[chunk_start:chunk_end]
        name = ctype.decode("latin-1", errors="replace")

        drop = False
        if ctype in _C2PA_CHUNK_TYPES or ctype.startswith(b"c2"):
            drop = True
            actions.append(f"drop PNG chunk {name} (C2PA/JUMBF)")
        elif ctype in _TEXT_CHUNK_TYPES:
            if strip_all_metadata:
                drop = True
                actions.append(f"drop PNG chunk {name}")
            elif contains_any(payload, AI_META_HINTS + C2PA_MARKERS):
                drop = True
                actions.append(f"drop PNG chunk {name} (AI/C2PA markers)")

        if not drop:
            out.extend(data[pos : chunk_end + 4])

        if ctype == b"IEND":
            break
        pos = chunk_end + 4

    if not actions:
        actions.append("no PNG metadata chunks removed (already clean or none matched)")
    return bytes(out), tuple(actions)


__all__ = ["supports", "inspect", "strip"]
