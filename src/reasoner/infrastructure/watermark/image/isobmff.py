"""AVIF/HEIC C2PA / AI-provenance metadata inspection and stripping.

Infrastructure layer: pure functions over bytes, no I/O. Recursive ISOBMFF
box-walk logic ported from the researched watermarks-remover project
(image_meta.py). AVIF and HEIC share the ISOBMFF container format; only the
`ftyp` brand differs, which detect_format() already resolves.
"""

from __future__ import annotations

import struct

from reasoner.core.ports.watermark_port import ImageFormat, ImageInspectReport, MarkFinding
from reasoner.domain.watermark.marks import MarkConfidence
from reasoner.infrastructure.watermark.image.detect import detect_format
from reasoner.infrastructure.watermark.image.markers import (
    AI_META_HINTS,
    C2PA_MARKERS,
    contains_any,
    is_confirmed_c2pa_hit,
)

# Per ISOBMFF/C2PA embedding convention: a 'uuid' box carrying this UUID holds
# an XMP packet rather than arbitrary vendor data.
XMP_UUID = b"\xbe\x7a\xcf\xcb\x97\xa9\x42\xe8\x9c\x71\x99\x94\x91\xe3\xaf\xac"

_C2PA_BOX_TYPES = (b"jumb", b"c2pa")


def supports(data: bytes) -> bool:
    return detect_format(data) in (ImageFormat.AVIF, ImageFormat.HEIC)


def _parse_boxes(data: bytes, start: int = 0, end: int | None = None) -> list[tuple[bytes, bytes, int, int]]:
    """Parse top-level or container ISOBMFF boxes.

    Returns (fourcc, payload, total_box_size, header_size) tuples. A box
    declaring more size than remains, or a malformed 64-bit-size extension
    header, ends parsing at that point rather than raising -- callers see
    everything parsed up to there.
    """
    if end is None:
        end = len(data)
    boxes: list[tuple[bytes, bytes, int, int]] = []
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        fourcc = data[pos + 4 : pos + 8]
        header_size = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - pos

        if size < header_size or pos + size > end:
            break
        payload = data[pos + header_size : pos + size]
        boxes.append((fourcc, payload, size, header_size))
        pos += size
    return boxes


def _is_c2pa_box(fourcc: bytes) -> bool:
    return fourcc in _C2PA_BOX_TYPES or fourcc.decode("latin-1", errors="replace").lower().startswith("c2")


def _format_for(data: bytes) -> ImageFormat:
    fmt = detect_format(data)
    return fmt if fmt in (ImageFormat.AVIF, ImageFormat.HEIC) else ImageFormat.UNKNOWN


def inspect(data: bytes) -> ImageInspectReport:
    fmt = _format_for(data)
    boxes = _parse_boxes(data)
    if not boxes:
        return ImageInspectReport(
            format=fmt,
            has_c2pa=False,
            has_ai_metadata=False,
            notes=(f"not a valid {fmt.value.upper()} (no ISOBMFF boxes)",),
        )

    findings: list[MarkFinding] = []
    has_c2pa = False
    has_ai = False

    def _scan_uuid(fourcc: bytes, payload: bytes, where: str) -> None:
        nonlocal has_c2pa, has_ai
        name = fourcc.decode("latin-1", errors="replace")
        if payload.startswith(XMP_UUID):
            has_ai = True
            findings.append(MarkFinding(f"{where} {name} box (XMP metadata)", MarkConfidence.INFORMATIONAL))
            return
        hits = contains_any(payload, AI_META_HINTS + C2PA_MARKERS)
        if hits:
            has_ai = True
            if is_confirmed_c2pa_hit(hits):
                has_c2pa = True
            findings.append(MarkFinding(f"{where} {name} box: {', '.join(hits[:8])}", MarkConfidence.PROBABLE))

    for fourcc, payload, _size, _hdr in boxes:
        name = fourcc.decode("latin-1", errors="replace")
        if _is_c2pa_box(fourcc):
            has_c2pa = True
            findings.append(MarkFinding(f"top-level {name} box (C2PA/JUMBF)", MarkConfidence.CONFIRMED))
            continue
        if fourcc == b"uuid":
            _scan_uuid(fourcc, payload, "top-level")
            continue
        if fourcc == b"meta":
            for s_fourcc, s_payload, _s_size, _s_hdr in _parse_boxes(payload, start=4):
                s_name = s_fourcc.decode("latin-1", errors="replace")
                if _is_c2pa_box(s_fourcc):
                    has_c2pa = True
                    findings.append(MarkFinding(f"meta sub-box {s_name} (C2PA/JUMBF)", MarkConfidence.CONFIRMED))
                    continue
                if s_fourcc == b"uuid":
                    _scan_uuid(s_fourcc, s_payload, "meta sub-box")
                    continue
                if s_fourcc in (b"xml ", b"bxml"):
                    hits = contains_any(s_payload, AI_META_HINTS + C2PA_MARKERS)
                    if hits:
                        has_ai = True
                        if is_confirmed_c2pa_hit(hits):
                            has_c2pa = True
                        findings.append(
                            MarkFinding(f"meta sub-box {s_name}: {', '.join(hits[:8])}", MarkConfidence.PROBABLE)
                        )

    return ImageInspectReport(
        format=fmt,
        has_c2pa=has_c2pa,
        has_ai_metadata=has_ai or has_c2pa,
        findings=tuple(findings),
    )


def strip(data: bytes, *, strip_all_metadata: bool = True) -> tuple[bytes, tuple[str, ...]]:
    fmt = _format_for(data)
    boxes = _parse_boxes(data)
    if not boxes:
        raise ValueError(f"not a valid {fmt.value.upper()} (no ISOBMFF boxes)")

    actions: list[str] = []
    out = bytearray()

    for fourcc, payload, _size, _hdr in boxes:
        name = fourcc.decode("latin-1", errors="replace")

        if _is_c2pa_box(fourcc):
            actions.append(f"drop top-level {name} box (C2PA/JUMBF)")
            continue

        if fourcc == b"uuid":
            if payload.startswith(XMP_UUID):
                actions.append(f"drop top-level {name} box (XMP metadata)")
                continue
            if strip_all_metadata or contains_any(payload, AI_META_HINTS + C2PA_MARKERS):
                actions.append(f"drop top-level {name} box (UUID metadata)")
                continue

        if fourcc == b"meta":
            meta_verflags = payload[:4] if len(payload) >= 4 else b"\x00\x00\x00\x00"
            clean_sub = bytearray()
            for s_fourcc, s_payload, _s_size, _s_hdr in _parse_boxes(payload, start=4):
                s_name = s_fourcc.decode("latin-1", errors="replace")
                if _is_c2pa_box(s_fourcc):
                    actions.append(f"drop meta sub-box {s_name} (C2PA/JUMBF)")
                    continue
                if s_fourcc == b"uuid":
                    if s_payload.startswith(XMP_UUID):
                        actions.append(f"drop meta sub-box {s_name} (XMP metadata)")
                        continue
                    if strip_all_metadata or contains_any(s_payload, AI_META_HINTS + C2PA_MARKERS):
                        actions.append(f"drop meta sub-box {s_name} (UUID metadata)")
                        continue
                if s_fourcc in (b"xml ", b"bxml"):
                    if strip_all_metadata or contains_any(s_payload, AI_META_HINTS + C2PA_MARKERS):
                        actions.append(f"drop meta sub-box {s_name} (XML metadata)")
                        continue
                clean_sub.extend(struct.pack(">I", len(s_payload) + 8) + s_fourcc + s_payload)

            new_meta_payload = meta_verflags + clean_sub
            out.extend(struct.pack(">I", len(new_meta_payload) + 8) + b"meta" + new_meta_payload)
            continue

        out.extend(struct.pack(">I", len(payload) + 8) + fourcc + payload)

    if not actions:
        actions.append(f"no {fmt.value.upper()} metadata boxes removed (already clean or none matched)")

    return bytes(out), tuple(actions)


__all__ = ["supports", "inspect", "strip", "XMP_UUID"]
