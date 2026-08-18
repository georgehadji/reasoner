"""Carrier taxonomy for edit-based Unicode watermark marks (Layer A).

Domain layer: pure data + context-free codepoint classification. No I/O, no
imports outside stdlib. Context-dependent preservation lives in rules.py.

Paper grounding: edit-based watermarking (invisible/format Unicode, homoglyph
spaces, confusable substitution) as distinct from generative/statistical
watermarking (biased token sampling) and file-provenance metadata (C2PA/XMP).
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum


class MarkKind(StrEnum):
    """Fine-grained classification of a detected carrier, for reporting."""

    ZWJ_FAMILY = "zwj_family"
    BIDI = "bidi"
    TAG_CHARS = "tag_chars"
    VARIATION_SELECTOR = "variation_selector"
    PRIVATE_USE = "private_use"
    SPACE_HOMOGLYPH = "space"
    CONFUSABLE = "confusable"
    OTHER_CF = "other_cf"
    STRIP = "strip"


class MarkConfidence(StrEnum):
    """How strong a finding is — a signal, not a verdict.

    Text Layer A only ever emits PROBABLE (edit-based carriers) and
    INFORMATIONAL (space homoglyphs, weaker context). CONFIRMED and
    LIKELY_FALSE_POSITIVE are reserved for the file/image metadata class
    (Phase 3), where "confirmed" means a recognized provenance structure and
    "likely_false_positive" means a raw byte-scan hit that can collide with
    compressed data. Declared together so text and image findings share one
    vocabulary end-to-end.
    """

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    INFORMATIONAL = "informational"
    LIKELY_FALSE_POSITIVE = "likely_false_positive"


def confidence_of(kind: MarkKind) -> MarkConfidence:
    """Text Layer A confidence: space homoglyphs are weaker context than carriers."""
    return MarkConfidence.INFORMATIONAL if kind == MarkKind.SPACE_HOMOGLYPH else MarkConfidence.PROBABLE


# ── Format / invisible controls commonly used for steganography or broken pastes ──
STRIP_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x00AD,  # soft hyphen
        0x034F,  # combining grapheme joiner
        0x061C,  # Arabic letter mark
        0x115F,  # Hangul choseong filler
        0x1160,  # Hangul jungseong filler
        0x17B4,  # Khmer vowel inherent AQ
        0x17B5,  # Khmer vowel inherent AA
        0x180B,  # Mongolian free variation selector-1
        0x180C,
        0x180D,
        0x180E,  # Mongolian vowel separator
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0x200E,  # LRM
        0x200F,  # RLM
        0x202A,  # LRE
        0x202B,  # RLE
        0x202C,  # PDF
        0x202D,  # LRO
        0x202E,  # RLO
        0x2060,  # word joiner
        0x2061,  # function application
        0x2062,  # invisible times
        0x2063,  # invisible separator
        0x2064,  # invisible plus
        0x2066,  # LRI
        0x2067,  # RLI
        0x2068,  # FSI
        0x2069,  # PDI
        0x206A,  # inhibit symmetric swapping
        0x206B,
        0x206C,
        0x206D,
        0x206E,
        0x206F,
        0xFEFF,  # BOM / ZWNBSP
        0xFE00,  # variation selectors
        0xFE01,
        0xFE02,
        0xFE03,
        0xFE04,
        0xFE05,
        0xFE06,
        0xFE07,
        0xFE08,
        0xFE09,
        0xFE0A,
        0xFE0B,
        0xFE0C,
        0xFE0D,
        0xFE0E,
        0xFE0F,
        0xFFF9,  # interlinear annotation
        0xFFFA,
        0xFFFB,
    }
)

# Spaces that look like (or substitute for) U+0020. Normalized, not deleted.
SPACE_HOMOGLYPHS: dict[int, str] = {
    0x00A0: " ",  # no-break space
    0x1680: " ",  # Ogham space mark
    0x2000: " ",  # en quad
    0x2001: " ",  # em quad
    0x2002: " ",  # en space
    0x2003: " ",  # em space
    0x2004: " ",  # three-per-em space
    0x2005: " ",  # four-per-em space
    0x2006: " ",  # six-per-em space
    0x2007: " ",  # figure space
    0x2008: " ",  # punctuation space
    0x2009: " ",  # thin space
    0x200A: " ",  # hair space
    0x202F: " ",  # narrow no-break space
    0x205F: " ",  # medium mathematical space
    0x3000: " ",  # ideographic space
}

# Confusable Latin lookalikes. Aggressive mode only, off by default: these are
# also real letters in Cyrillic and CJK-fullwidth contexts, so blind
# replacement is a false-positive risk normal prose can hit.
LATIN_CONFUSABLES: dict[int, str] = {
    0x0410: "A",  # Cyrillic
    0x0412: "B",
    0x0415: "E",
    0x041A: "K",
    0x041C: "M",
    0x041D: "H",
    0x041E: "O",
    0x0420: "P",
    0x0421: "C",
    0x0422: "T",
    0x0425: "X",
    0x0430: "a",
    0x0435: "e",
    0x043E: "o",
    0x0440: "p",
    0x0441: "c",
    0x0443: "y",
    0x0445: "x",
    0x0456: "i",
    0xFF21: "A",  # fullwidth
    0xFF22: "B",
    0xFF23: "C",
    0xFF24: "D",
    0xFF25: "E",
    0xFF26: "F",
    0xFF27: "G",
    0xFF28: "H",
    0xFF29: "I",
    0xFF2A: "J",
    0xFF2B: "K",
    0xFF2C: "L",
    0xFF2D: "M",
    0xFF2E: "N",
    0xFF2F: "O",
    0xFF30: "P",
    0xFF31: "Q",
    0xFF32: "R",
    0xFF33: "S",
    0xFF34: "T",
    0xFF35: "U",
    0xFF36: "V",
    0xFF37: "W",
    0xFF38: "X",
    0xFF39: "Y",
    0xFF3A: "Z",
    0xFF41: "a",
    0xFF42: "b",
    0xFF43: "c",
    0xFF44: "d",
    0xFF45: "e",
    0xFF46: "f",
    0xFF47: "g",
    0xFF48: "h",
    0xFF49: "i",
    0xFF4A: "j",
    0xFF4B: "k",
    0xFF4C: "l",
    0xFF4D: "m",
    0xFF4E: "n",
    0xFF4F: "o",
    0xFF50: "p",
    0xFF51: "q",
    0xFF52: "r",
    0xFF53: "s",
    0xFF54: "t",
    0xFF55: "u",
    0xFF56: "v",
    0xFF57: "w",
    0xFF58: "x",
    0xFF59: "y",
    0xFF5A: "z",
}

# Variation selectors beyond FE0x (VS17-VS256, Supplementary Special-purpose Plane)
VS_SUPPLEMENT: range = range(0xE0100, 0xE01F0)

# Unicode tag characters (U+E0001-E007F) — the classic invisible-instruction
# smuggling channel. E0020-E007E double as flag-emoji subdivision tags; see
# rules.py FlagTagRule for the context under which that run is load-bearing.
TAG_RANGE: range = range(0xE0001, 0xE0080)
_FLAG_TAG_RANGE: range = range(0xE0020, 0xE0080)  # excludes the E0001 language-tag start

# Bidi / directional format controls (subset of STRIP_CODEPOINTS, finer inspect labels)
BIDI_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x061C,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    }
)

# Directional marks and isolates are legitimate in mixed RTL/LTR prose and are
# preserved by default. Embeddings/overrides (LRE/RLE/LRO/RLO) stay
# destructive by default because they can reorder unrelated spans; complete
# LRE/RLE...PDF *embedding* pairs (not overrides) are the one exception,
# handled contextually in rules.py since it requires scanning for the match.
PRESERVABLE_BIDI_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x061C,
        0x200E,
        0x200F,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    }
)

BIDI_EMBEDDING_OPENERS: frozenset[int] = frozenset({0x202A, 0x202B})
BIDI_OVERRIDE_OPENERS: frozenset[int] = frozenset({0x202D, 0x202E})
BIDI_POP_DIRECTIONAL_FORMATTING: int = 0x202C

# Reporting classification only (used by strip_kind, not by preservation
# rules): the "zero-width family" bucket a stripped hit is labelled under.
# Deliberately a standalone set rather than derived from EMOJI_GLUE_CODEPOINTS
# / SCRIPT_JOINER_CODEPOINTS -- ZWSP (0x200B) and word joiner (0x2060) are
# never load-bearing (no preservation rule ever keeps them) but still belong
# in this reporting bucket, not the generic "strip" catch-all.
ZW_FAMILY_CODEPOINTS: frozenset[int] = frozenset({0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E})

# Emoji presentation glue: zero-width joiner and text/emoji variation
# selectors. Invisible carriers when free-floating, but part of the visible
# sequence after an emoji base (⚖️, 👨‍👩‍👧, ❤️‍🔥) — stripping them there
# visibly alters the text.
EMOJI_GLUE_CODEPOINTS: frozenset[int] = frozenset({0x200D, 0xFE0E, 0xFE0F})

# ZWNJ/ZWJ are orthographic inside complex scripts (Persian می‌روم, Devanagari
# क्‍ष) when joining two letters of the same script.
SCRIPT_JOINER_CODEPOINTS: frozenset[int] = frozenset({0x200C, 0x200D})

# A handful of Cf codepoints are normal Arabic/Syriac/Kaithi orthography, not carriers.
ORTHOGRAPHIC_CF_CODEPOINTS: frozenset[int] = frozenset(
    {0x0600, 0x0601, 0x0602, 0x0603, 0x0604, 0x0605, 0x06DD, 0x070F, 0x08E2, 0x110BD, 0x110CD}
)

# Mongolian free variation selectors choose a glyph of the preceding letter;
# Khmer inherent vowels are invisible but phonemic; Hangul fillers hold a jamo
# slot in a partial syllable. Each is only meaningful directly after a base
# from its own script — isolated instances are contraband.
MONGOLIAN_FVS_CODEPOINTS: frozenset[int] = frozenset({0x180B, 0x180C, 0x180D})
KHMER_INHERENT_VOWEL_CODEPOINTS: frozenset[int] = frozenset({0x17B4, 0x17B5})
HANGUL_FILLER_CODEPOINTS: frozenset[int] = frozenset({0x115F, 0x1160})

# The waving-black-flag base a complete subdivision-flag tag sequence starts from.
FLAG_SEQUENCE_BASE: int = 0x1F3F4


def is_private_use(cp: int) -> bool:
    """BMP and supplementary private-use planes (category Co: no portable meaning)."""
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def is_variation_selector(cp: int) -> bool:
    return cp in VS_SUPPLEMENT or 0xFE00 <= cp <= 0xFE0F or 0x180B <= cp <= 0x180D


def is_tag_char(cp: int) -> bool:
    return cp in TAG_RANGE


def is_glue_codepoint(cp: int) -> bool:
    """Load-bearing invisible: emoji/CJK glue, script joiner, tag char, or same-script filler.

    Used only to decide whether a kept-or-replaced character should advance
    "the previous surviving base letter" for subsequent same-script rules.
    Glue characters do not advance it, so a ZWJ chain (👨‍👩‍👧) or a joiner run
    stays bound to the base before the glue, not to the glue itself.
    """
    return (
        cp in EMOJI_GLUE_CODEPOINTS
        or is_variation_selector(cp)
        or cp in SCRIPT_JOINER_CODEPOINTS
        or is_tag_char(cp)
        or cp in MONGOLIAN_FVS_CODEPOINTS
        or cp in KHMER_INHERENT_VOWEL_CODEPOINTS
        or cp in HANGUL_FILLER_CODEPOINTS
    )


def is_strip_codepoint(cp: int) -> bool:
    """Context-free: True if this codepoint is a carrier regardless of neighbours."""
    return (
        cp in STRIP_CODEPOINTS
        or cp in VS_SUPPLEMENT
        or is_tag_char(cp)
        or is_private_use(cp)
    )


def strip_kind(cp: int) -> MarkKind:
    """Fine-grained inspect kind for a codepoint already known to be a carrier."""
    if is_tag_char(cp):
        return MarkKind.TAG_CHARS
    if cp in VS_SUPPLEMENT or 0xFE00 <= cp <= 0xFE0F or 0x180B <= cp <= 0x180D:
        return MarkKind.VARIATION_SELECTOR
    if cp in BIDI_CODEPOINTS:
        return MarkKind.BIDI
    if cp in ZW_FAMILY_CODEPOINTS:
        return MarkKind.ZWJ_FAMILY
    if is_private_use(cp):
        return MarkKind.PRIVATE_USE
    return MarkKind.STRIP


def is_cjk_ideograph(cp: int) -> bool:
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x323AF
    )


def is_mongolian_letter(cp: int) -> bool:
    return 0x1800 <= cp <= 0x18AF and unicodedata.category(chr(cp))[0] == "L"


def is_khmer_letter(cp: int) -> bool:
    return 0x1780 <= cp <= 0x17FF and unicodedata.category(chr(cp))[0] == "L"


def is_hangul_jamo(cp: int) -> bool:
    return (
        0x1100 <= cp <= 0x11FF
        or 0xA960 <= cp <= 0xA97C  # Hangul Jamo Extended-A
        or 0xD7B0 <= cp <= 0xD7C6  # Hangul Jamo Extended-B
    )


def is_emoji_base(cp: int) -> bool:
    """True for characters that can start or continue an emoji sequence."""
    if 0x1F000 <= cp <= 0x1FAFF:
        return True
    if 0x2190 <= cp <= 0x25FF:  # arrows, technical symbols, enclosed symbols
        return True
    if 0x2600 <= cp <= 0x27BF:  # misc symbols / dingbats / arrows
        return True
    if 0x2B00 <= cp <= 0x2BFF:  # misc symbols and arrows
        return True
    if cp in (0x00A9, 0x00AE, 0x2122, 0x3030, 0x303D, 0x3297, 0x3299):
        return True
    if cp in (0x0023, 0x002A) or 0x0030 <= cp <= 0x0039:  # keycap bases
        return True
    return False


_SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0600, 0x08FF, "arabic"),
    (0x0900, 0x0DFF, "indic"),
    (0x0F00, 0x109F, "south-asian"),
    (0x1780, 0x17FF, "khmer"),
    (0x1800, 0x18AF, "mongolian"),
)


def joining_script(cp: int) -> str | None:
    """Broad script group where ZWJ/ZWNJ can be orthographic, or None."""
    for start, end, name in _SCRIPT_RANGES:
        if start <= cp <= end and unicodedata.category(chr(cp))[0] in ("L", "M"):
            return name
    return None


__all__ = [
    "MarkKind",
    "MarkConfidence",
    "confidence_of",
    "STRIP_CODEPOINTS",
    "SPACE_HOMOGLYPHS",
    "LATIN_CONFUSABLES",
    "VS_SUPPLEMENT",
    "TAG_RANGE",
    "BIDI_CODEPOINTS",
    "PRESERVABLE_BIDI_CODEPOINTS",
    "BIDI_EMBEDDING_OPENERS",
    "BIDI_OVERRIDE_OPENERS",
    "BIDI_POP_DIRECTIONAL_FORMATTING",
    "ZW_FAMILY_CODEPOINTS",
    "EMOJI_GLUE_CODEPOINTS",
    "SCRIPT_JOINER_CODEPOINTS",
    "ORTHOGRAPHIC_CF_CODEPOINTS",
    "MONGOLIAN_FVS_CODEPOINTS",
    "KHMER_INHERENT_VOWEL_CODEPOINTS",
    "HANGUL_FILLER_CODEPOINTS",
    "FLAG_SEQUENCE_BASE",
    "is_private_use",
    "is_variation_selector",
    "is_tag_char",
    "is_glue_codepoint",
    "is_strip_codepoint",
    "strip_kind",
    "is_cjk_ideograph",
    "is_mongolian_letter",
    "is_khmer_letter",
    "is_hangul_jamo",
    "is_emoji_base",
    "joining_script",
]
