"""Layer A: edit-based Unicode watermark inspection and scrubbing.

The public surface is two functions sharing one implementation (ADR-7):
`scrub_text()` does the work; `inspect_text()` is scrub_text().report with the
transformed text discarded. There is exactly one code path from "classify
every character" to "report what would change" -- inspect can never predict
something scrub then does differently, because they are the same call.

Domain layer: pure functions over str, no I/O, no async, no external state.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum, auto

from reasoner.domain.watermark.marks import (
    BIDI_EMBEDDING_OPENERS,
    BIDI_OVERRIDE_OPENERS,
    BIDI_POP_DIRECTIONAL_FORMATTING,
    FLAG_SEQUENCE_BASE,
    LATIN_CONFUSABLES,
    SPACE_HOMOGLYPHS,
    MarkKind,
    is_glue_codepoint,
    is_strip_codepoint,
    strip_kind,
)
from reasoner.domain.watermark.report import CharHit, ScrubResult, ScrubStats, TextInspectReport, char_label
from reasoner.domain.watermark.rules import (
    CharContext,
    PreservationRule,
    ScrubOptions,
    active_rules_for,
)
from reasoner.domain.watermark.spans import ProtectedSpans, detect_protected_spans

DEFAULT_OPTIONS = ScrubOptions()
_EMPTY_SPANS = ProtectedSpans()

_TAG_RUN_START = 0xE0020
_TAG_RUN_END = 0xE007E  # inclusive
_TAG_TERMINATOR = 0xE007F
_CJK_VS_FE_END = 0xFE0D  # inclusive; FE0E/FE0F are emoji presentation, handled by EmojiGlueRule


class Action(Enum):
    KEEP = auto()
    STRIP = auto()
    REPLACE = auto()


@dataclass(frozen=True, slots=True)
class Decision:
    """One character's verdict. `kind` is None whenever nothing is reportable —
    both for ordinary kept characters and for characters preserved by a rule."""

    action: Action
    out_char: str  # "" for STRIP
    kind: MarkKind | None


@dataclass(frozen=True, slots=True)
class ScanIndex:
    """Pre-scanned index sets so classify() never backtracks per character."""

    flag_sequence_indices: frozenset[int]
    bidi_embedding_indices: frozenset[int]

    def in_flag_sequence(self, index: int) -> bool:
        return index in self.flag_sequence_indices

    def in_bidi_embedding(self, index: int) -> bool:
        return index in self.bidi_embedding_indices


def _scan_flag_sequences(text: str) -> frozenset[int]:
    """Indices of tag chars + terminator inside a complete subdivision-flag run.

    A run is FLAG_SEQUENCE_BASE (waving black flag) followed by one or more
    tag chars (E0020-E007E) and a terminator (E007F). Incomplete runs (no
    terminator found) contribute nothing -- their tag chars stay contraband.
    """
    valid: set[int] = set()
    i = 0
    n = len(text)
    while i < n:
        if ord(text[i]) != FLAG_SEQUENCE_BASE:
            i += 1
            continue
        j = i + 1
        while j < n and _TAG_RUN_START <= ord(text[j]) <= _TAG_RUN_END:
            j += 1
        if j > i + 1 and j < n and ord(text[j]) == _TAG_TERMINATOR:
            valid.update(range(i + 1, j + 1))
            i = j + 1
        else:
            i += 1
    return frozenset(valid)


def _scan_bidi_embeddings(text: str) -> frozenset[int]:
    """Indices of the LRE/RLE and matching PDF in each complete embedding pair.

    Only the pair's two control-character positions are marked -- the text
    between them is untouched regardless. Overrides (LRO/RLO) are tracked on
    the same stack so nesting resolves correctly, but their indices are never
    added: they stay destructive by default (they can reorder unrelated spans).
    """
    valid: set[int] = set()
    stack: list[tuple[int, int]] = []
    for index, ch in enumerate(text):
        cp = ord(ch)
        if cp in BIDI_EMBEDDING_OPENERS or cp in BIDI_OVERRIDE_OPENERS:
            stack.append((cp, index))
        elif cp == BIDI_POP_DIRECTIONAL_FORMATTING:
            if not stack:
                continue
            opener_cp, opener_index = stack.pop()
            if opener_cp in BIDI_EMBEDDING_OPENERS:
                valid.add(opener_index)
                valid.add(index)
    return frozenset(valid)


def build_scan_index(text: str) -> ScanIndex:
    return ScanIndex(
        flag_sequence_indices=_scan_flag_sequences(text),
        bidi_embedding_indices=_scan_bidi_embeddings(text),
    )


def classify(
    ctx: CharContext,
    active_rules: tuple[PreservationRule, ...],
    opts: ScrubOptions,
    *,
    protected: bool = False,
) -> Decision:
    """Decide one character's fate. Rule precedence is fixed: a preservation
    rule wins over everything else, so a character both "load-bearing" and
    "matches a carrier table" (e.g. a script joiner that happens to be in
    SCRIPT_JOINER_CODEPOINTS) is kept.
    """
    if any(rule.preserves(ctx) for rule in active_rules):
        return Decision(Action.KEEP, chr(ctx.cp), None)
    if is_strip_codepoint(ctx.cp):
        return Decision(Action.STRIP, "", strip_kind(ctx.cp))
    if opts.normalize_spaces and ctx.cp in SPACE_HOMOGLYPHS:
        return Decision(Action.REPLACE, SPACE_HOMOGLYPHS[ctx.cp], MarkKind.SPACE_HOMOGLYPH)
    if opts.aggressive_confusables and not protected and ctx.cp in LATIN_CONFUSABLES:
        return Decision(Action.REPLACE, LATIN_CONFUSABLES[ctx.cp], MarkKind.CONFUSABLE)
    if unicodedata.category(chr(ctx.cp)) == "Cf" and ctx.cp not in SPACE_HOMOGLYPHS:
        return Decision(Action.STRIP, "", MarkKind.OTHER_CF)
    return Decision(Action.KEEP, chr(ctx.cp), None)


def _iter_decisions(
    text: str, opts: ScrubOptions
) -> Iterator[tuple[int, int, Decision]]:
    """The one pass both scrub_text and inspect_text (via scrub_text) drive.

    Yields (index, original_codepoint, decision) for every character. Builds
    the ScanIndex and protected spans once, up front, and threads prev_kept
    across the loop so same-script/glue rules see the real preceding base.
    """
    scan = build_scan_index(text)
    active_rules = active_rules_for(opts)
    needs_spans = opts.aggressive_confusables or opts.nfkc
    protected_spans = detect_protected_spans(text) if needs_spans else _EMPTY_SPANS

    prev_kept: int | None = None
    n = len(text)
    for i, ch in enumerate(text):
        cp = ord(ch)
        ctx = CharContext(
            cp=cp,
            prev_kept=prev_kept,
            prev_input=ord(text[i - 1]) if i > 0 else None,
            next_input=ord(text[i + 1]) if i + 1 < n else None,
            in_flag_sequence=scan.in_flag_sequence(i),
            in_bidi_embedding=scan.in_bidi_embedding(i),
        )
        decision = classify(ctx, active_rules, opts, protected=protected_spans.covers(i))
        yield i, cp, decision

        if decision.action != Action.STRIP and not is_glue_codepoint(cp):
            prev_kept = ord(decision.out_char) if decision.out_char else cp


def _apply_protected_nfkc(chars: list[str], protected: list[bool]) -> tuple[str, int]:
    """NFKC-normalize contiguous unprotected runs; protected runs pass through untouched.

    Segmenting by protection status (rather than normalizing the whole string
    and hoping protected substrings survived) is what ADR-6 requires: a
    Cyrillic lookalike or fullwidth digit inside a URL or code fence must not
    be canonicalized away.
    """
    if not chars:
        return "", 0
    segments: list[tuple[str, bool]] = []
    run_start = 0
    for i in range(1, len(chars) + 1):
        if i == len(chars) or protected[i] != protected[run_start]:
            segments.append(("".join(chars[run_start:i]), protected[run_start]))
            run_start = i

    out_parts: list[str] = []
    changed_total = 0
    for segment_text, is_protected in segments:
        if is_protected or not segment_text:
            out_parts.append(segment_text)
            continue
        normalized = unicodedata.normalize("NFKC", segment_text)
        out_parts.append(normalized)
        if normalized != segment_text:
            changed_total += sum(
                end - start
                for op, start, end, _new_start, _new_end in SequenceMatcher(
                    None, segment_text, normalized, autojunk=False
                ).get_opcodes()
                if op != "equal"
            )
    return "".join(out_parts), changed_total


def _build_hits(buckets: dict[tuple[int, MarkKind], list[int]]) -> tuple[CharHit, ...]:
    hits = []
    for (cp, kind), offsets in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0][0])):
        hits.append(
            CharHit(
                codepoint=cp,
                char=chr(cp),
                label=char_label(cp),
                count=len(offsets),
                kind=kind,
                samples=tuple(offsets[:10]),
            )
        )
    return tuple(hits)


_NOTES_BASE: tuple[str, ...] = (
    "Layer A only: invisible/format Unicode and space homoglyphs (edit-based carriers).",
    "Statistical (token-sampling) watermarks are not detectable here; use Layer B rewrite.",
    "Inspect kinds: strip, bidi, tag_chars, variation_selector, zwj_family, private_use, "
    "space, confusable, other_cf.",
    "Load-bearing invisibles are preserved by default during cleaning: emoji glue, CJK/"
    "Mongolian variation selectors, script joiners, complete flag tag sequences, "
    "same-script fillers/selectors (Mongolian FVS, Khmer inherent vowels, Hangul jamo "
    "fillers), RTL directional marks/paired embeddings, and orthographic Arabic/Syriac Cf "
    "marks. Inspection still reports bidi controls. Use explicit strip flags only after review.",
)
_NOTE_CLEAN = (
    "No deterministic Layer A (invisible Unicode/format) carriers detected; "
    "statistical and pixel-domain marks are out of scope here."
)


def _default_notes(has_hits: bool) -> tuple[str, ...]:
    return _NOTES_BASE if has_hits else _NOTES_BASE + (_NOTE_CLEAN,)


def scrub_text(text: str, opts: ScrubOptions = DEFAULT_OPTIONS) -> ScrubResult:
    """Remove/normalize edit-based Unicode carriers; report what was found and changed."""
    buckets: dict[tuple[int, MarkKind], list[int]] = {}
    out_chars: list[str] = []
    out_protected: list[bool] = []
    removed: dict[str, int] = {}
    replaced: dict[str, int] = {}

    needs_spans = opts.aggressive_confusables or opts.nfkc
    protected_spans = detect_protected_spans(text) if needs_spans else _EMPTY_SPANS

    for i, cp, decision in _iter_decisions(text, opts):
        if decision.kind is not None:
            buckets.setdefault((cp, decision.kind), []).append(i)

        if decision.action == Action.STRIP:
            label = char_label(cp)
            removed[label] = removed.get(label, 0) + 1
            continue

        out_chars.append(decision.out_char)
        out_protected.append(protected_spans.covers(i))
        if decision.action == Action.REPLACE:
            label = char_label(cp)
            replaced[label] = replaced.get(label, 0) + 1

    nfkc_changed_count = 0
    if opts.nfkc:
        result_text, nfkc_changed_count = _apply_protected_nfkc(out_chars, out_protected)
    else:
        result_text = "".join(out_chars)

    hits = _build_hits(buckets)
    suspicious_total = sum(len(offsets) for offsets in buckets.values())
    report = TextInspectReport(
        length=len(text),
        suspicious_total=suspicious_total,
        hits=hits,
        notes=_default_notes(bool(hits)),
    )
    stats = ScrubStats(
        input_length=len(text),
        output_length=len(result_text),
        removed=tuple(sorted(removed.items())),
        replaced=tuple(sorted(replaced.items())),
        nfkc_changed_count=nfkc_changed_count,
    )
    return ScrubResult(text=result_text, report=report, stats=stats)


def inspect_text(text: str, opts: ScrubOptions = DEFAULT_OPTIONS) -> TextInspectReport:
    """Read-only: what scrub_text would find and change, without changing anything.

    Implemented as scrub_text(text, opts).report -- there is no second
    classification path to drift out of sync with (ADR-7).
    """
    return scrub_text(text, opts).report


__all__ = [
    "DEFAULT_OPTIONS",
    "Action",
    "Decision",
    "ScanIndex",
    "build_scan_index",
    "classify",
    "scrub_text",
    "inspect_text",
]
