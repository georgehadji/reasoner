"""JPEG C2PA / AI-provenance metadata inspection and stripping.

Infrastructure layer: pure functions over bytes, no I/O. Marker-walk logic
ported from the researched watermarks-remover project (image_meta.py). The
entropy-coded scan (SOS through EOF) is copied through byte-for-byte on
strip -- rewriting it is out of scope and would corrupt the image.
"""

from __future__ import annotations

import struct

from reasoner.core.ports.watermark_port import ImageFormat, ImageInspectReport, MarkFinding
from reasoner.domain.watermark.marks import MarkConfidence
from reasoner.infrastructure.watermark.image.detect import JPEG_SOI
from reasoner.infrastructure.watermark.image.markers import (
    AI_META_HINTS,
    C2PA_MARKERS,
    MAX_STRUCTURES,
    cap_findings,
    contains_any,
    count_actions,
    is_confirmed_c2pa_hit,
    structure_limit_error,
)

_APP11_JUMBF = 0xEB  # APP11: JUMBF/C2PA common
_APPN_SCANNED = (0xE1, 0xE2, 0xED, 0xEE, 0xEB)  # APP1/2/13/14/11
_RESTART_LO, _RESTART_HI = 0xD0, 0xD7
_MARKER_SOI, _MARKER_EOI, _MARKER_SOS, _MARKER_COM = 0xD8, 0xD9, 0xDA, 0xFE
_APPN_LO, _APPN_HI = 0xE0, 0xEF
_APP0_JFIF = 0xE0


def _tally(actions: dict[str, int], action: str) -> None:
    actions[action] = actions.get(action, 0) + 1


def supports(data: bytes) -> bool:
    return data.startswith(JPEG_SOI)


def inspect(data: bytes) -> ImageInspectReport:
    if not supports(data):
        return ImageInspectReport(
            format=ImageFormat.JPEG,
            has_c2pa=False,
            has_ai_metadata=False,
            notes=("not a JPEG",),
        )

    findings: list[MarkFinding] = []
    has_c2pa = False
    has_ai = False
    i = 2
    n = len(data)
    walked = 0
    while i + 2 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        while i < n and data[i] == 0xFF:  # fill bytes are legal before a marker
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        walked += 1
        if walked > MAX_STRUCTURES:
            raise structure_limit_error("JPEG segments")
        if marker in (_MARKER_SOI, _MARKER_EOI):
            continue
        if marker == _MARKER_SOS:  # entropy-coded scan follows -- stop scanning
            break
        if _RESTART_LO <= marker <= _RESTART_HI:
            continue
        if i + 2 > n:
            break
        seglen = struct.unpack(">H", data[i : i + 2])[0]
        if seglen < 2 or i + seglen > n:
            findings.append(
                MarkFinding(f"bad segment length at marker 0x{marker:02X}", MarkConfidence.INFORMATIONAL)
            )
            break
        payload = data[i + 2 : i + seglen]
        i += seglen

        if marker == _APP11_JUMBF:
            has_c2pa = True
            findings.append(MarkFinding("JPEG APP11 segment (JUMBF/C2PA common)", MarkConfidence.CONFIRMED))
        if marker in _APPN_SCANNED:
            hits = contains_any(payload, AI_META_HINTS + C2PA_MARKERS)
            if hits:
                has_ai = True
                if is_confirmed_c2pa_hit(hits):
                    has_c2pa = True
                findings.append(
                    MarkFinding(f"JPEG APP{marker - 0xE0}: {', '.join(hits[:8])}", MarkConfidence.PROBABLE)
                )

    whole = contains_any(data, C2PA_MARKERS)
    if whole and not has_c2pa:
        has_c2pa = True
        findings.append(
            MarkFinding(
                f"byte-scan C2PA markers: {', '.join(whole[:6])}",
                MarkConfidence.LIKELY_FALSE_POSITIVE,
            )
        )

    return ImageInspectReport(
        format=ImageFormat.JPEG,
        has_c2pa=has_c2pa,
        has_ai_metadata=has_ai or has_c2pa,
        findings=cap_findings(findings)[0],
        notes=cap_findings(findings)[1],
    )


def strip(data: bytes, *, strip_all_metadata: bool = True) -> tuple[bytes, tuple[str, ...]]:
    """Drop APP11 (JUMBF/C2PA) always, other APPn per policy, and all COM segments.

    APP0 (JFIF) is kept even under strip_all_metadata=True for decoder
    compatibility. The entropy-coded scan (SOS onward) is copied through
    verbatim once reached.
    """
    if not supports(data):
        raise ValueError("not a JPEG")

    actions: dict[str, int] = {}
    out = bytearray(data[:2])  # SOI
    i = 2
    n = len(data)
    walked = 0
    while i + 2 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        walked += 1
        if walked > MAX_STRUCTURES:
            raise structure_limit_error("JPEG segments")

        if marker == _MARKER_EOI:
            out.extend(bytes([0xFF, _MARKER_EOI]))
            break
        if marker == _MARKER_SOI:
            continue
        if _RESTART_LO <= marker <= _RESTART_HI:
            out.extend(bytes([0xFF, marker]))
            continue
        if marker == _MARKER_SOS:
            if i + 2 > n:
                break
            out.extend(bytes([0xFF, _MARKER_SOS]))
            out.extend(data[i:])
            actions["preserved entropy-coded scan (SOS->EOF)"] = 1
            break

        if i + 2 > n:
            break
        seglen = struct.unpack(">H", data[i : i + 2])[0]
        if seglen < 2 or i + seglen > n:
            out.extend(data[i - 2 :])
            actions["truncated segment; copied remainder"] = 1
            break
        payload = data[i + 2 : i + seglen]
        next_i = i + seglen

        keep = False
        drop = False
        if _APPN_LO <= marker <= _APPN_HI:
            if marker == _APP11_JUMBF:
                drop = True
                _tally(actions, "drop APP11 (C2PA/JUMBF)")
            elif strip_all_metadata and marker != _APP0_JFIF:
                drop = True
                _tally(actions, f"drop APP{marker - 0xE0}")
            elif contains_any(payload, AI_META_HINTS + C2PA_MARKERS):
                drop = True
                _tally(actions, f"drop APP{marker - 0xE0} (AI/C2PA markers)")
            else:
                keep = True
        elif marker == _MARKER_COM:
            drop = True
            _tally(actions, "drop COM comment")
        else:
            keep = True

        if keep and not drop:
            out.extend(bytes([0xFF, marker]))
            out.extend(data[i : i + seglen])
        i = next_i

    if not actions:
        actions["no JPEG APP segments removed"] = 1
    return bytes(out), count_actions(actions)


__all__ = ["supports", "inspect", "strip"]
