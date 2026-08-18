"""Layer A end-to-end: classify() dispatch, ScanIndex, inspect_text, scrub_text.

The false-positive corpus below is the point of this module: a naive strip of
every invisible/format Unicode codepoint corrupts real text. Each case here
pins one class of load-bearing invisible that must survive a default clean --
this is what replaces the buggy reasoner.core.sanitization.clean_llm_artifacts
(see docs/plans/watermark-removal-integration.md Part II, "the existing Layer
A and why it must be replaced").

This file is pure ASCII source. Every non-ASCII fixture is built from
explicit chr(codepoint) calls, never typed as a literal invisible/exotic
character in the source -- there is no reliable way to eyeball-verify (or
round-trip through tooling) that a zero-width joiner or a Mongolian vowel
sign was transcribed correctly, so ambiguity is not an option here. Every
codepoint below is cross-checked against the tables in
domain/watermark/marks.py.
"""

from __future__ import annotations

from reasoner.domain.watermark.layer_a import (
    Action,
    Decision,
    build_scan_index,
    classify,
    inspect_text,
    scrub_text,
)
from reasoner.domain.watermark.marks import MarkKind
from reasoner.domain.watermark.rules import CharContext, ScrubOptions, active_rules_for

DEFAULT = ScrubOptions()


def _ctx(cp: int, **kwargs) -> CharContext:
    return CharContext(cp=cp, **kwargs)


def _s(*codepoints: int) -> str:
    """Build a string from explicit codepoints -- the only way non-ASCII text enters this file."""
    return "".join(chr(cp) for cp in codepoints)


# ── Named fixtures ──────────────────────────────────────────────────────────

ZWSP = _s(0x200B)
ZWJ = _s(0x200D)
ZWNJ = _s(0x200C)
BOM = _s(0xFEFF)
NBSP = _s(0x00A0)
VS16 = _s(0xFE0F)
LRM = _s(0x200E)
RLM = _s(0x200F)
LRI, PDI = _s(0x2066), _s(0x2069)
RLE, RLO, PDF = _s(0x202B), _s(0x202E), _s(0x202C)

MAN, WOMAN, GIRL, BOY = _s(0x1F468), _s(0x1F469), _s(0x1F467), _s(0x1F466)
HEAVY_BLACK_HEART = _s(0x2764)
FIRE = _s(0x1F525)
BALANCE_SCALE = _s(0x2696)

WAVING_BLACK_FLAG = _s(0x1F3F4)
# Tag chars spell "gbsct" (ISO 3166-2 GB-SCT, Scotland): U+E0000 + ord(ascii letter).
TAG_G, TAG_B, TAG_S, TAG_C, TAG_T = _s(0xE0067), _s(0xE0062), _s(0xE0073), _s(0xE0063), _s(0xE0074)
TAG_TERMINATOR = _s(0xE007F)
SCOTLAND_FLAG = WAVING_BLACK_FLAG + TAG_G + TAG_B + TAG_S + TAG_C + TAG_T + TAG_TERMINATOR

# Persian mi-ravam ("I go"): MEEM, FARSI YEH, ZWNJ, REH, WAW, MEEM.
PERSIAN_MEEM, PERSIAN_YEH, PERSIAN_REH, PERSIAN_WAW = _s(0x0645), _s(0x06CC), _s(0x0631), _s(0x0648)
PERSIAN_MIRAVAM = PERSIAN_MEEM + PERSIAN_YEH + ZWNJ + PERSIAN_REH + PERSIAN_WAW + PERSIAN_MEEM

# Devanagari conjunct ksha: KA, VIRAMA, ZWJ, SSA.
DEVANAGARI_KA, DEVANAGARI_VIRAMA, DEVANAGARI_SSA = _s(0x0915), _s(0x094D), _s(0x0937)
DEVANAGARI_KSHA = DEVANAGARI_KA + DEVANAGARI_VIRAMA + ZWJ + DEVANAGARI_SSA

MONGOLIAN_LETTER_A = _s(0x1820)
MONGOLIAN_FVS1 = _s(0x180B)
KHMER_LETTER_KA = _s(0x1780)
KHMER_VOWEL_INHERENT_AQ = _s(0x17B4)
HANGUL_CHOSEONG_KIYEOK = _s(0x1100)
HANGUL_CHOSEONG_FILLER = _s(0x115F)

ARABIC_NUMBER_SIGN = _s(0x0600)
SYRIAC_ABBREVIATION_MARK = _s(0x070F)

# "Hebrew" spelled in Hebrew: AYIN, BET, REISH, YOD, TAV.
HEBREW_IVRIT = _s(0x05E2, 0x05D1, 0x05E8, 0x05D9, 0x05EA)

FULLWIDTH_AB = _s(0xFF21, 0xFF22)  # fullwidth Latin A, B
CYRILLIC_A = _s(0x0410)


# ── classify() dispatcher, unit-level ──────────────────────────────────────


class TestClassifyDispatch:
    def test_ordinary_ascii_is_kept_with_no_kind(self):
        d = classify(_ctx(0x0041), active_rules_for(DEFAULT), DEFAULT)  # 'A'
        assert d == Decision(Action.KEEP, "A", None)

    def test_zwsp_is_stripped(self):
        d = classify(_ctx(ord(ZWSP)), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.STRIP
        assert d.out_char == ""
        assert d.kind is MarkKind.ZWJ_FAMILY

    def test_tag_char_outside_flag_sequence_is_stripped(self):
        d = classify(_ctx(ord(TAG_G), in_flag_sequence=False), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.STRIP
        assert d.kind is MarkKind.TAG_CHARS

    def test_private_use_is_stripped(self):
        d = classify(_ctx(0xE000), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.STRIP
        assert d.kind is MarkKind.PRIVATE_USE

    def test_nbsp_is_replaced_with_ascii_space(self):
        d = classify(_ctx(ord(NBSP)), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.REPLACE
        assert d.out_char == " "
        assert d.kind is MarkKind.SPACE_HOMOGLYPH

    def test_space_normalization_can_be_disabled(self):
        opts = ScrubOptions(normalize_spaces=False)
        d = classify(_ctx(ord(NBSP)), active_rules_for(opts), opts)
        # Falls through to the Cf check; NBSP is category Zs, not Cf, so it is kept.
        assert d.action is Action.KEEP

    def test_confusable_kept_by_default(self):
        opts = ScrubOptions()  # aggressive_confusables=False
        d = classify(_ctx(ord(CYRILLIC_A)), active_rules_for(opts), opts)
        assert d.action is Action.KEEP

    def test_confusable_replaced_when_aggressive(self):
        opts = ScrubOptions(aggressive_confusables=True)
        d = classify(_ctx(ord(CYRILLIC_A)), active_rules_for(opts), opts)
        assert d.action is Action.REPLACE
        assert d.out_char == "A"
        assert d.kind is MarkKind.CONFUSABLE

    def test_confusable_kept_when_protected_even_if_aggressive(self):
        opts = ScrubOptions(aggressive_confusables=True)
        d = classify(_ctx(ord(CYRILLIC_A)), active_rules_for(opts), opts, protected=True)
        assert d.action is Action.KEEP

    def test_bidi_carrier_is_stripped_when_strip_bidi_disables_its_rule(self):
        opts = ScrubOptions(strip_bidi=True)
        d = classify(_ctx(0x061C), active_rules_for(opts), opts)  # Arabic Letter Mark
        assert d.action is Action.STRIP

    def test_generic_cf_fallback_catches_codepoints_outside_every_table(self):
        # U+1BCA0 SHORTHAND FORMAT LETTER OVERLAP: category Cf, not in
        # STRIP_CODEPOINTS/SPACE_HOMOGLYPHS/ORTHOGRAPHIC_CF_CODEPOINTS, not
        # matched by any preservation rule -- exercises the final Cf
        # catch-all branch in classify(), not any explicit table lookup.
        d = classify(_ctx(0x1BCA0), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.STRIP
        assert d.kind is MarkKind.OTHER_CF

    def test_rule_precedence_beats_carrier_strip(self):
        # LRM is both a PRESERVABLE_BIDI_CODEPOINT (rule keeps it) and in
        # STRIP_CODEPOINTS (would otherwise be stripped) -- the rule wins.
        d = classify(_ctx(ord(LRM)), active_rules_for(DEFAULT), DEFAULT)
        assert d.action is Action.KEEP


# ── ScanIndex ───────────────────────────────────────────────────────────────


class TestScanIndexFlagSequences:
    def test_complete_flag_sequence_indices_are_valid(self):
        scan = build_scan_index(SCOTLAND_FLAG)
        for i in range(1, len(SCOTLAND_FLAG)):
            assert scan.in_flag_sequence(i) is True
        assert scan.in_flag_sequence(0) is False  # the base flag itself isn't a tag char

    def test_incomplete_flag_sequence_is_not_valid(self):
        text = WAVING_BLACK_FLAG + TAG_G  # no terminator
        scan = build_scan_index(text)
        assert scan.in_flag_sequence(1) is False

    def test_tag_char_without_base_is_not_valid(self):
        scan = build_scan_index(TAG_G)
        assert scan.in_flag_sequence(0) is False


class TestScanIndexBidiEmbeddings:
    def test_complete_lre_pdf_pair_is_valid(self):
        text = "a" + RLE + "b" + PDF + "c"
        scan = build_scan_index(text)
        assert scan.in_bidi_embedding(1) is True  # RLE
        assert scan.in_bidi_embedding(3) is True  # PDF
        assert scan.in_bidi_embedding(0) is False
        assert scan.in_bidi_embedding(2) is False  # content between is untouched either way

    def test_override_pair_is_not_valid(self):
        text = "a" + RLO + "b" + PDF + "c"
        scan = build_scan_index(text)
        assert scan.in_bidi_embedding(1) is False
        assert scan.in_bidi_embedding(3) is False

    def test_unmatched_pdf_is_ignored(self):
        text = "a" + PDF + "b"
        scan = build_scan_index(text)
        assert scan.in_bidi_embedding(1) is False

    def test_nested_embeddings_resolve_via_stack(self):
        lre = _s(0x202A)
        text = lre + RLE + "x" + PDF + PDF
        scan = build_scan_index(text)
        assert all(scan.in_bidi_embedding(i) for i in (0, 1, 3, 4))


# ── inspect_text / scrub_text: default-option carrier removal ──────────────


class TestBasicCarrierRemoval:
    def test_zwsp_removed_by_default(self):
        result = scrub_text("Hello" + ZWSP + "World")
        assert result.text == "HelloWorld"
        assert result.stats.removed_count == 1

    def test_bom_removed_by_default(self):
        result = scrub_text(BOM + "Hello")
        assert result.text == "Hello"

    def test_tag_chars_removed_by_default(self):
        # The invisible-instruction smuggling channel the old
        # clean_llm_artifacts implementation missed entirely.
        payload = "Hello" + _s(0xE0041, 0xE0042, 0xE0043) + "World"
        result = scrub_text(payload)
        assert result.text == "HelloWorld"
        assert result.stats.removed_count == 3

    def test_private_use_removed_by_default(self):
        payload = "Hello" + _s(0xE001) + "World"
        result = scrub_text(payload)
        assert result.text == "HelloWorld"

    def test_nbsp_normalized_to_ascii_space(self):
        result = scrub_text("Hello" + NBSP + "World")
        assert result.text == "Hello World"
        assert result.stats.replaced_count == 1

    def test_plain_ascii_is_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = scrub_text(text)
        assert result.text == text
        assert result.stats.total_changed == 0


# ── False-positive corpus: load-bearing invisibles must survive ────────────


class TestEmojiZwjFamiliesSurvive:
    def test_family_emoji_zwj_sequence_survives(self):
        family = MAN + ZWJ + WOMAN + ZWJ + GIRL
        result = scrub_text(family)
        assert result.text == family
        assert result.stats.total_changed == 0

    def test_heart_on_fire_survives(self):
        heart_fire = HEAVY_BLACK_HEART + VS16 + ZWJ + FIRE
        result = scrub_text(heart_fire)
        assert result.text == heart_fire

    def test_vs16_after_emoji_base_survives(self):
        text = BALANCE_SCALE + VS16
        result = scrub_text(text)
        assert result.text == text

    def test_free_floating_zwj_is_still_stripped(self):
        # Not after/between emoji bases -- contraband, matches the old
        # behavior for the actually-dangerous case.
        text = "Hello" + ZWJ + "World"
        result = scrub_text(text)
        assert result.text == "HelloWorld"


class TestFlagSequencesSurvive:
    def test_subdivision_flag_survives(self):
        result = scrub_text(SCOTLAND_FLAG)
        assert result.text == SCOTLAND_FLAG
        assert result.stats.total_changed == 0


class TestScriptJoinersSurvive:
    def test_persian_zwnj_survives(self):
        result = scrub_text(PERSIAN_MIRAVAM)
        assert result.text == PERSIAN_MIRAVAM
        assert result.stats.total_changed == 0

    def test_devanagari_zwj_conjunct_survives(self):
        result = scrub_text(DEVANAGARI_KSHA)
        assert result.text == DEVANAGARI_KSHA

    def test_zwnj_between_latin_letters_is_still_stripped(self):
        # Latin isn't a joining script -- ordinary contraband ZWNJ.
        text = "a" + ZWNJ + "b"
        result = scrub_text(text)
        assert result.text == "ab"


class TestSameScriptFillersSurvive:
    def test_mongolian_free_variation_selector_survives(self):
        text = MONGOLIAN_LETTER_A + MONGOLIAN_FVS1
        result = scrub_text(text)
        assert result.text == text

    def test_khmer_inherent_vowel_survives(self):
        text = KHMER_LETTER_KA + KHMER_VOWEL_INHERENT_AQ
        result = scrub_text(text)
        assert result.text == text

    def test_hangul_filler_in_partial_syllable_survives(self):
        text = HANGUL_CHOSEONG_KIYEOK + HANGUL_CHOSEONG_FILLER
        result = scrub_text(text)
        assert result.text == text

    def test_mongolian_fvs_without_mongolian_base_is_stripped(self):
        text = "a" + MONGOLIAN_FVS1 + "b"
        result = scrub_text(text)
        assert result.text == "ab"


class TestOrthographicArabicMarksSurvive:
    def test_arabic_number_sign_survives(self):
        text = ARABIC_NUMBER_SIGN + "123"
        result = scrub_text(text)
        assert result.text == text

    def test_syriac_abbreviation_mark_survives(self):
        text = "a" + SYRIAC_ABBREVIATION_MARK + "b"
        result = scrub_text(text)
        assert result.text == text


class TestBidiIsolatesAndMarksSurvive:
    def test_rtl_mark_survives(self):
        text = "hello" + RLM + "world"
        result = scrub_text(text)
        assert result.text == text

    def test_directional_isolates_survive_mixed_rtl_ltr(self):
        text = "See " + LRI + HEBREW_IVRIT + PDI + " word"
        result = scrub_text(text)
        assert result.text == text

    def test_complete_lre_embedding_pair_survives(self):
        text = "a" + RLE + "b" + PDF + "c"
        result = scrub_text(text)
        assert result.text == text

    def test_override_is_still_stripped_by_default(self):
        # LRO/RLO can reorder unrelated spans -- destructive by default,
        # unlike embeddings.
        text = "a" + RLO + "b" + PDF + "c"
        result = scrub_text(text)
        assert RLO not in result.text

    def test_strip_bidi_option_strips_everything_bidi(self):
        text = "hello" + RLM + "world"
        result = scrub_text(text, ScrubOptions(strip_bidi=True))
        assert result.text == "helloworld"


class TestStripEmojiGlueParanoidMode:
    def test_strip_emoji_glue_removes_load_bearing_zwj(self):
        family = MAN + ZWJ + WOMAN
        result = scrub_text(family, ScrubOptions(strip_emoji_glue=True))
        assert ZWJ not in result.text

    def test_strip_emoji_glue_does_not_touch_bidi(self):
        text = "hello" + RLM + "world"
        result = scrub_text(text, ScrubOptions(strip_emoji_glue=True))
        assert result.text == text


# ── The specific corruption bugs in the old implementation ─────────────────


class TestOldImplementationCorruptionIsFixed:
    """core.sanitization.clean_llm_artifacts unconditionally stripped ZWJ and
    all bidi controls. Pin the exact cases that broke."""

    def test_emoji_zwj_family_not_collapsed(self):
        family = MAN + ZWJ + WOMAN + ZWJ + GIRL
        assert scrub_text(family).text == family

    def test_persian_orthography_not_corrupted(self):
        assert scrub_text(PERSIAN_MIRAVAM).text == PERSIAN_MIRAVAM

    def test_rtl_isolate_not_stripped_from_mixed_prose(self):
        text = "The word is " + LRI + HEBREW_IVRIT + PDI + " in Hebrew."
        assert scrub_text(text).text == text


# ── prev_kept / glue advancement ─────────────────────────────────────────


class TestPrevKeptAdvancement:
    def test_glue_does_not_break_chain_across_stripped_carrier(self):
        # Mongolian letter, then a contraband ZWSP, then FVS: prev_kept must
        # still see the Mongolian letter (the ZWSP is stripped, and stripped
        # characters never advance prev_kept -- see _iter_decisions).
        text = MONGOLIAN_LETTER_A + ZWSP + MONGOLIAN_FVS1
        result = scrub_text(text)
        assert result.text == MONGOLIAN_LETTER_A + MONGOLIAN_FVS1

    def test_multi_join_zwj_chain_stays_bound_to_original_base(self):
        # Four-person family: each ZWJ must see the *base* two hops back as
        # emoji, not the previous ZWJ.
        family = MAN + ZWJ + WOMAN + ZWJ + GIRL + ZWJ + BOY
        result = scrub_text(family)
        assert result.text == family


# ── NFKC + protected spans ──────────────────────────────────────────────


class TestNfkcProtectedSpans:
    def test_nfkc_off_by_default(self):
        result = scrub_text(FULLWIDTH_AB)
        assert result.text == FULLWIDTH_AB
        assert result.stats.nfkc_changed is False

    def test_nfkc_normalizes_fullwidth_when_enabled(self):
        result = scrub_text(FULLWIDTH_AB, ScrubOptions(nfkc=True))
        assert result.text == "AB"
        assert result.stats.nfkc_changed is True
        assert result.stats.nfkc_changed_count > 0

    def test_nfkc_does_not_touch_url(self):
        text = "see https://example.com/" + FULLWIDTH_AB + " now"
        result = scrub_text(text, ScrubOptions(nfkc=True))
        assert FULLWIDTH_AB in result.text  # inside the URL, untouched

    def test_nfkc_still_normalizes_outside_protected_spans(self):
        text = FULLWIDTH_AB + " https://example.com/" + FULLWIDTH_AB
        result = scrub_text(text, ScrubOptions(nfkc=True))
        assert result.text.startswith("AB ")
        assert FULLWIDTH_AB in result.text  # the URL copy survives

    def test_confusable_not_touched_inside_code_fence(self):
        text = "```\n" + CYRILLIC_A + "\n```"
        result = scrub_text(text, ScrubOptions(aggressive_confusables=True))
        assert CYRILLIC_A in result.text


# ── inspect_text mirrors scrub_text exactly ─────────────────────────────


class TestInspectMirrorsScrub:
    def test_inspect_reports_same_total_as_scrub_changes(self):
        text = "Hello" + ZWSP + "World Test"
        report = inspect_text(text)
        result = scrub_text(text)
        assert report.suspicious_total == result.stats.total_changed
        assert report.to_dict() == result.report.to_dict()

    def test_inspect_on_clean_text_reports_zero(self):
        report = inspect_text("Nothing suspicious here.")
        assert report.suspicious_total == 0
        assert report.hits == ()

    def test_hits_carry_confidence_and_samples(self):
        report = inspect_text("a" + ZWSP + "b" + ZWSP + "c")
        assert len(report.hits) == 1
        hit = report.hits[0]
        assert hit.count == 2
        assert hit.kind is MarkKind.ZWJ_FAMILY
        assert hit.samples == (1, 3)

    def test_space_hits_are_informational_confidence(self):
        report = inspect_text("a" + NBSP + "b")
        assert report.hits[0].to_dict()["confidence"] == "informational"

    def test_strip_hits_are_probable_confidence(self):
        report = inspect_text("a" + ZWSP + "b")
        assert report.hits[0].to_dict()["confidence"] == "probable"
