"""Context-dependent preservation rules for Layer A Unicode scrubbing.

Specification pattern: each rule is an independent predicate "does this
character's context make it load-bearing?" over an immutable CharContext.
Replaces a single 68-line if-ladder (branches for bidi, emoji glue, CJK
variation selectors, script joiners, flag sequences, same-script fillers, and
orthographic marks all threaded through shared flags) with one small class
per concern. Adding a script exemption means adding a rule, not editing
classify() in layer_a.py.

Domain layer: pure predicates over ints, no I/O, no imports outside stdlib
and marks.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from reasoner.domain.watermark.marks import (
    BIDI_POP_DIRECTIONAL_FORMATTING,
    EMOJI_GLUE_CODEPOINTS,
    HANGUL_FILLER_CODEPOINTS,
    KHMER_INHERENT_VOWEL_CODEPOINTS,
    MONGOLIAN_FVS_CODEPOINTS,
    ORTHOGRAPHIC_CF_CODEPOINTS,
    PRESERVABLE_BIDI_CODEPOINTS,
    SCRIPT_JOINER_CODEPOINTS,
    TAG_RANGE,
    is_cjk_ideograph,
    is_emoji_base,
    is_hangul_jamo,
    is_khmer_letter,
    is_mongolian_letter,
    is_variation_selector,
    joining_script,
)

_CJK_FE_RANGE_END = 0xFE0D  # inclusive; distinct from the emoji VS15/VS16 pair (FE0E/FE0F)


@dataclass(frozen=True, slots=True)
class CharContext:
    """Everything a preservation rule may consult. Immutable, index-free.

    `prev_kept` is the last character that survived classification and is not
    itself glue (see layer_a.py) -- it is what "the preceding letter" means
    for filler/joiner rules, so a stripped or glue character in between does
    not break the chain. `prev_input`/`next_input` are the raw neighbours in
    the original text, used by rules that care about surface adjacency (e.g.
    emoji-base detection) regardless of what survives.
    """

    cp: int
    prev_kept: int | None = None
    prev_input: int | None = None
    next_input: int | None = None
    in_flag_sequence: bool = False
    in_bidi_embedding: bool = False


@runtime_checkable
class PreservationRule(Protocol):
    """A named predicate: should this codepoint survive, given its context?"""

    def preserves(self, ctx: CharContext) -> bool: ...


@dataclass(frozen=True, slots=True)
class BidiDirectionalRule:
    """RTL isolates/marks and complete LRE/RLE...PDF embedding pairs.

    Overrides (LRO/RLO) are excluded even though they share a strip flag with
    embeddings: they can reorder unrelated spans and stay destructive by
    default. `in_bidi_embedding` is only ever true for embedding-pair
    members (see layer_a.ScanIndex), never for overrides, so no extra check
    is needed here to exclude them.
    """

    def preserves(self, ctx: CharContext) -> bool:
        if ctx.in_bidi_embedding:
            return True
        return ctx.cp in PRESERVABLE_BIDI_CODEPOINTS


@dataclass(frozen=True, slots=True)
class EmojiGlueRule:
    """ZWJ and VS15/VS16 immediately adjacent to an emoji base.

    VS15/VS16 need only the preceding raw character; ZWJ needs both a
    surviving emoji base before it and a raw emoji base after it, since ZWJ
    joins two presentation units rather than modifying one.
    """

    def preserves(self, ctx: CharContext) -> bool:
        if ctx.cp not in EMOJI_GLUE_CODEPOINTS:
            return False
        if ctx.cp in (0xFE0E, 0xFE0F):
            return ctx.prev_input is not None and is_emoji_base(ctx.prev_input)
        if ctx.cp == 0x200D:
            return (
                ctx.prev_kept is not None
                and ctx.next_input is not None
                and is_emoji_base(ctx.prev_kept)
                and is_emoji_base(ctx.next_input)
            )
        return False


@dataclass(frozen=True, slots=True)
class CjkVariationSelectorRule:
    """Variation selectors immediately after a CJK ideograph.

    Selects an Ideographic Variation Database glyph variant of the preceding
    character -- distinct from emoji presentation glue (EmojiGlueRule) and
    from same-script fillers (SameScriptFillerRule), which key off different
    base scripts and different codepoint ranges.
    """

    def preserves(self, ctx: CharContext) -> bool:
        if ctx.prev_input is None or not is_cjk_ideograph(ctx.prev_input):
            return False
        return is_variation_selector(ctx.cp) or (0xFE00 <= ctx.cp <= _CJK_FE_RANGE_END)


@dataclass(frozen=True, slots=True)
class ScriptJoinerRule:
    """ZWNJ/ZWJ joining two letters/marks of the same complex script.

    Orthographic inside Arabic (می‌روم), Devanagari (क्‍ष), and other joining
    scripts -- contraband when free-floating or spanning a script boundary.
    """

    def preserves(self, ctx: CharContext) -> bool:
        if ctx.cp not in SCRIPT_JOINER_CODEPOINTS:
            return False
        if ctx.prev_input is None or ctx.next_input is None:
            return False
        prev_script = joining_script(ctx.prev_input)
        next_script = joining_script(ctx.next_input)
        return prev_script is not None and prev_script == next_script


@dataclass(frozen=True, slots=True)
class FlagTagRule:
    """Tag characters inside a complete subdivision-flag sequence (🏴‍☠️-style)."""

    def preserves(self, ctx: CharContext) -> bool:
        return ctx.cp in TAG_RANGE and ctx.in_flag_sequence


@dataclass(frozen=True, slots=True)
class SameScriptFillerRule:
    """Mongolian FVS / Khmer inherent vowel / Hangul filler after their own base.

    Each holds meaning only directly after a letter of its own script --
    isolated instances are contraband. Keyed on prev_kept (the last surviving
    letter), not prev_input, so a stripped carrier in between does not break
    the chain.
    """

    def preserves(self, ctx: CharContext) -> bool:
        if ctx.prev_kept is None:
            return False
        if ctx.cp in MONGOLIAN_FVS_CODEPOINTS:
            return is_mongolian_letter(ctx.prev_kept)
        if ctx.cp in KHMER_INHERENT_VOWEL_CODEPOINTS:
            return is_khmer_letter(ctx.prev_kept)
        if ctx.cp in HANGUL_FILLER_CODEPOINTS:
            return is_hangul_jamo(ctx.prev_kept)
        return False


@dataclass(frozen=True, slots=True)
class OrthographicCfRule:
    """A fixed set of Arabic/Syriac/Kaithi format marks that are normal orthography.

    Unconditional -- unlike every other rule here, these are never contraband
    regardless of context, so no gating flag gets to disable this one.
    """

    def preserves(self, ctx: CharContext) -> bool:
        return ctx.cp in ORTHOGRAPHIC_CF_CODEPOINTS


@dataclass(frozen=True, slots=True)
class ScrubOptions:
    """Resolved policy for one inspect/scrub call. Immutable, hashable.

    Each False->True flip on `strip_bidi` / `strip_emoji_glue` deactivates a
    group of preservation rules (see active_rules_for) rather than being
    threaded through the classifier per character.
    """

    normalize_spaces: bool = True
    aggressive_confusables: bool = False
    strip_emoji_glue: bool = False
    strip_bidi: bool = False
    nfkc: bool = False


# Order matters only for readability; classify() short-circuits on the first
# rule that preserves, and the rules are mutually exclusive in practice (each
# keys off a disjoint codepoint set).
_BIDI_RULES: tuple[PreservationRule, ...] = (BidiDirectionalRule(),)
_GLUE_RULES: tuple[PreservationRule, ...] = (
    EmojiGlueRule(),
    CjkVariationSelectorRule(),
    ScriptJoinerRule(),
    FlagTagRule(),
    SameScriptFillerRule(),
)
_ALWAYS_RULES: tuple[PreservationRule, ...] = (OrthographicCfRule(),)


def active_rules_for(opts: ScrubOptions) -> tuple[PreservationRule, ...]:
    """Resolve which preservation rules apply for one scrub, given its options.

    Computed once per call, outside the character loop, so classify() never
    re-checks an option flag per character.
    """
    rules: tuple[PreservationRule, ...] = _ALWAYS_RULES
    if not opts.strip_bidi:
        rules += _BIDI_RULES
    if not opts.strip_emoji_glue:
        rules += _GLUE_RULES
    return rules


__all__ = [
    "CharContext",
    "PreservationRule",
    "BidiDirectionalRule",
    "EmojiGlueRule",
    "CjkVariationSelectorRule",
    "ScriptJoinerRule",
    "FlagTagRule",
    "SameScriptFillerRule",
    "OrthographicCfRule",
    "ScrubOptions",
    "active_rules_for",
]
