"""Property-based tests for the four Layer A domain invariants (ADR-7, plan Part V.1).

These are the guarantees the whole design rests on:
  - idempotence: a second scrub of already-scrubbed text finds nothing left to do
  - inspect predicts scrub: inspect_text can never predict something scrub_text
    then does differently
  - ASCII identity: plain printable ASCII is never touched
  - never lengthens: scrubbing only removes or 1:1-replaces (without NFKC --
    NFKC compatibility decomposition can expand a ligature into multiple
    codepoints, so that invariant is scoped to nfkc=False)

A fifth check exercises ADR-6 directly: content inside a protected span (code
fence, URL) survives confusable and NFKC normalization untouched.

Hypothesis explores far more of the codepoint space than the hand-written
corpus in test_watermark_layer_a.py; a shrunk failing example here is the
fastest way to find the next false-positive class.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from reasoner.domain.watermark.layer_a import inspect_text, scrub_text
from reasoner.domain.watermark.rules import ScrubOptions

_ASCII_PRINTABLE_PLUS_WS = [chr(c) for c in range(0x20, 0x7F)] + ["\n", "\t"]

_text_strategy = st.text(max_size=200)
_ascii_text_strategy = st.text(alphabet=_ASCII_PRINTABLE_PLUS_WS, max_size=200)

_options_strategy = st.builds(
    ScrubOptions,
    normalize_spaces=st.booleans(),
    aggressive_confusables=st.booleans(),
    strip_emoji_glue=st.booleans(),
    strip_bidi=st.booleans(),
    nfkc=st.booleans(),
)
_options_no_nfkc_strategy = st.builds(
    ScrubOptions,
    normalize_spaces=st.booleans(),
    aggressive_confusables=st.booleans(),
    strip_emoji_glue=st.booleans(),
    strip_bidi=st.booleans(),
    nfkc=st.just(False),
)


@settings(max_examples=200, deadline=None)
@given(text=_text_strategy, opts=_options_strategy)
def test_idempotence(text, opts):
    once = scrub_text(text, opts)
    twice = scrub_text(once.text, opts)
    assert twice.stats.total_changed == 0


@settings(max_examples=200, deadline=None)
@given(text=_text_strategy, opts=_options_strategy)
def test_inspect_predicts_scrub(text, opts):
    report = inspect_text(text, opts)
    result = scrub_text(text, opts)
    assert report.suspicious_total == result.stats.total_changed


@settings(max_examples=200, deadline=None)
@given(text=_ascii_text_strategy, opts=_options_strategy)
def test_ascii_identity(text, opts):
    result = scrub_text(text, opts)
    assert result.text == text
    assert result.stats.total_changed == 0


@settings(max_examples=200, deadline=None)
@given(text=_text_strategy, opts=_options_no_nfkc_strategy)
def test_never_lengthens_without_nfkc(text, opts):
    result = scrub_text(text, opts)
    assert len(result.text) <= len(text)


@settings(max_examples=100, deadline=None)
@given(
    prefix=st.text(alphabet=_ASCII_PRINTABLE_PLUS_WS, max_size=30),
    suffix=st.text(alphabet=_ASCII_PRINTABLE_PLUS_WS, max_size=30),
)
def test_code_fence_content_survives_aggressive_normalization(prefix, suffix):
    # Cyrillic confusable 'A' + fullwidth digit '1' -- both would normally be
    # rewritten under aggressive_confusables/nfkc, except inside a fence.
    inner = chr(0x0410) + chr(0xFF11)
    text = f"{prefix}```\n{inner}\n```{suffix}"
    result = scrub_text(text, ScrubOptions(aggressive_confusables=True, nfkc=True))
    assert inner in result.text


@settings(max_examples=100, deadline=None)
@given(
    prefix=st.text(alphabet=_ASCII_PRINTABLE_PLUS_WS, max_size=30),
    suffix=st.text(alphabet=_ASCII_PRINTABLE_PLUS_WS, max_size=30),
)
def test_url_content_survives_aggressive_normalization(prefix, suffix):
    inner = chr(0x0410) + chr(0xFF11)
    text = f"{prefix} https://example.com/{inner} {suffix}"
    result = scrub_text(text, ScrubOptions(aggressive_confusables=True, nfkc=True))
    assert inner in result.text
