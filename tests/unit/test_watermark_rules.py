"""Preservation-rule specifications for Layer A Unicode scrubbing.

Each rule is an independent, testable predicate over CharContext: "should this
codepoint survive, given what surrounds it?" Replaces a single 68-line
if-ladder (the reference watermarks-remover implementation) with the
Specification pattern so a new script exemption is a new rule, not a new
branch threaded through existing ones.

Fixtures here double as the false-positive corpus: emoji ZWJ families, flag
sequences, Persian/Devanagari script joiners, Mongolian/Khmer/Hangul fillers,
orthographic Arabic marks, and RTL isolates must all survive a default clean.
"""

from __future__ import annotations

import pytest

from reasoner.domain.watermark.rules import (
    BidiDirectionalRule,
    CharContext,
    CjkVariationSelectorRule,
    EmojiGlueRule,
    FlagTagRule,
    OrthographicCfRule,
    SameScriptFillerRule,
    ScriptJoinerRule,
    ScrubOptions,
    active_rules_for,
)


def ctx(
    cp: int,
    *,
    prev_kept: int | None = None,
    prev_input: int | None = None,
    next_input: int | None = None,
    in_flag_sequence: bool = False,
    in_bidi_embedding: bool = False,
) -> CharContext:
    return CharContext(
        cp=cp,
        prev_kept=prev_kept,
        prev_input=prev_input,
        next_input=next_input,
        in_flag_sequence=in_flag_sequence,
        in_bidi_embedding=in_bidi_embedding,
    )


class TestCharContextImmutable:
    def test_frozen(self):
        c = ctx(0x200D)
        with pytest.raises(AttributeError):
            c.cp = 0x0041  # type: ignore[misc]


class TestScrubOptionsImmutable:
    def test_frozen(self):
        opts = ScrubOptions()
        with pytest.raises(AttributeError):
            opts.strip_bidi = True  # type: ignore[misc]

    def test_defaults_are_conservative(self):
        opts = ScrubOptions()
        assert opts.normalize_spaces is True
        assert opts.aggressive_confusables is False
        assert opts.strip_emoji_glue is False
        assert opts.strip_bidi is False
        assert opts.nfkc is False


class TestBidiDirectionalRule:
    rule = BidiDirectionalRule()

    def test_preserves_lrm(self):
        assert self.rule.preserves(ctx(0x200E)) is True

    def test_preserves_rtl_isolate(self):
        assert self.rule.preserves(ctx(0x2066)) is True  # LRI
        assert self.rule.preserves(ctx(0x2069)) is True  # PDI

    def test_preserves_complete_embedding_pair_member(self):
        assert self.rule.preserves(ctx(0x202A, in_bidi_embedding=True)) is True

    def test_does_not_preserve_override(self):
        # LRO/RLO can reorder unrelated spans -- destructive by default.
        assert self.rule.preserves(ctx(0x202D)) is False
        assert self.rule.preserves(ctx(0x202E)) is False

    def test_does_not_preserve_unrelated_codepoint(self):
        assert self.rule.preserves(ctx(0x0041)) is False


class TestEmojiGlueRule:
    rule = EmojiGlueRule()
    EMOJI_BASE = 0x1F600  # grinning face

    def test_preserves_vs16_after_emoji_base(self):
        assert self.rule.preserves(ctx(0xFE0F, prev_input=self.EMOJI_BASE)) is True

    def test_preserves_vs15_after_emoji_base(self):
        assert self.rule.preserves(ctx(0xFE0E, prev_input=self.EMOJI_BASE)) is True

    def test_preserves_zwj_between_emoji_bases(self):
        # prev_kept AND next_input both emoji bases -- e.g. the join in a ZWJ family.
        assert (
            self.rule.preserves(
                ctx(0x200D, prev_kept=self.EMOJI_BASE, next_input=self.EMOJI_BASE)
            )
            is True
        )

    def test_does_not_preserve_vs16_after_plain_letter(self):
        assert self.rule.preserves(ctx(0xFE0F, prev_input=0x0041)) is False

    def test_does_not_preserve_zwj_without_next_emoji_base(self):
        assert self.rule.preserves(ctx(0x200D, prev_kept=self.EMOJI_BASE, next_input=0x0041)) is False

    def test_does_not_preserve_free_floating_zwj(self):
        assert self.rule.preserves(ctx(0x200D)) is False


class TestCjkVariationSelectorRule:
    rule = CjkVariationSelectorRule()
    CJK_IDEOGRAPH = 0x4E2D  # 中

    def test_preserves_supplement_vs_after_cjk(self):
        assert self.rule.preserves(ctx(0xE0100, prev_input=self.CJK_IDEOGRAPH)) is True

    def test_preserves_fe0x_vs_after_cjk(self):
        assert self.rule.preserves(ctx(0xFE00, prev_input=self.CJK_IDEOGRAPH)) is True

    def test_does_not_preserve_vs_after_latin(self):
        assert self.rule.preserves(ctx(0xFE00, prev_input=0x0041)) is False

    def test_does_not_preserve_without_prev_input(self):
        assert self.rule.preserves(ctx(0xFE00)) is False


class TestScriptJoinerRule:
    rule = ScriptJoinerRule()
    # Persian: می‌روم -- ZWNJ (200C) joins two Arabic-script letters.
    PERSIAN_MI = 0x06CC  # ی
    PERSIAN_RAVAM = 0x0631  # ر

    def test_preserves_zwnj_between_same_script_letters(self):
        assert (
            self.rule.preserves(
                ctx(0x200C, prev_input=self.PERSIAN_MI, next_input=self.PERSIAN_RAVAM)
            )
            is True
        )

    def test_preserves_zwj_between_devanagari_letters(self):
        devanagari_ka = 0x0915
        devanagari_ssa = 0x0937
        assert (
            self.rule.preserves(
                ctx(0x200D, prev_input=devanagari_ka, next_input=devanagari_ssa)
            )
            is True
        )

    def test_does_not_preserve_across_different_scripts(self):
        assert self.rule.preserves(ctx(0x200C, prev_input=self.PERSIAN_MI, next_input=0x0041)) is False

    def test_does_not_preserve_free_floating(self):
        assert self.rule.preserves(ctx(0x200C)) is False


class TestFlagTagRule:
    rule = FlagTagRule()

    def test_preserves_tag_char_in_complete_flag_sequence(self):
        assert self.rule.preserves(ctx(0xE0067, in_flag_sequence=True)) is True

    def test_does_not_preserve_tag_char_outside_flag_sequence(self):
        assert self.rule.preserves(ctx(0xE0067, in_flag_sequence=False)) is False


class TestSameScriptFillerRule:
    rule = SameScriptFillerRule()
    MONGOLIAN_LETTER = 0x1820
    KHMER_LETTER = 0x1780
    HANGUL_JAMO = 0x1100

    def test_preserves_mongolian_fvs_after_mongolian_letter(self):
        assert self.rule.preserves(ctx(0x180B, prev_kept=self.MONGOLIAN_LETTER)) is True

    def test_preserves_khmer_vowel_after_khmer_letter(self):
        assert self.rule.preserves(ctx(0x17B4, prev_kept=self.KHMER_LETTER)) is True

    def test_preserves_hangul_filler_after_hangul_jamo(self):
        assert self.rule.preserves(ctx(0x115F, prev_kept=self.HANGUL_JAMO)) is True

    def test_does_not_preserve_mongolian_fvs_after_unrelated_char(self):
        assert self.rule.preserves(ctx(0x180B, prev_kept=0x0041)) is False

    def test_does_not_preserve_without_prev_kept(self):
        assert self.rule.preserves(ctx(0x180B)) is False


class TestOrthographicCfRule:
    rule = OrthographicCfRule()

    def test_preserves_arabic_number_sign(self):
        assert self.rule.preserves(ctx(0x0600)) is True

    def test_preserves_syriac_abbreviation_mark(self):
        assert self.rule.preserves(ctx(0x070F)) is True

    def test_does_not_preserve_unrelated_codepoint(self):
        assert self.rule.preserves(ctx(0x200B)) is False

    def test_unconditional_no_context_needed(self):
        # No prev/next required -- always preserved regardless of neighbours.
        assert self.rule.preserves(ctx(0x0600, prev_kept=None, next_input=None)) is True


class TestActiveRulesFor:
    def test_default_options_activate_all_but_none(self):
        rules = active_rules_for(ScrubOptions())
        names = {type(r).__name__ for r in rules}
        assert names == {
            "BidiDirectionalRule",
            "EmojiGlueRule",
            "CjkVariationSelectorRule",
            "ScriptJoinerRule",
            "FlagTagRule",
            "SameScriptFillerRule",
            "OrthographicCfRule",
        }

    def test_strip_bidi_deactivates_only_bidi_rule(self):
        rules = active_rules_for(ScrubOptions(strip_bidi=True))
        names = {type(r).__name__ for r in rules}
        assert "BidiDirectionalRule" not in names
        assert "EmojiGlueRule" in names
        assert "OrthographicCfRule" in names

    def test_strip_emoji_glue_deactivates_glue_family_not_bidi_or_orthographic(self):
        rules = active_rules_for(ScrubOptions(strip_emoji_glue=True))
        names = {type(r).__name__ for r in rules}
        assert names == {"BidiDirectionalRule", "OrthographicCfRule"}

    def test_both_flags_leave_only_orthographic(self):
        rules = active_rules_for(ScrubOptions(strip_bidi=True, strip_emoji_glue=True))
        names = {type(r).__name__ for r in rules}
        assert names == {"OrthographicCfRule"}

    def test_result_is_a_tuple(self):
        assert isinstance(active_rules_for(ScrubOptions()), tuple)
