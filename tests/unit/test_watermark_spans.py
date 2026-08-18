"""Protected-span detection: code fences, inline code, URLs, markdown link targets.

Only normalizing decisions (confusable substitution, NFKC) consult these
spans -- carrier stripping ignores them by design (see spans.py module doc).
"""

from __future__ import annotations

from reasoner.domain.watermark.spans import ProtectedSpans, detect_protected_spans


class TestProtectedSpansCovers:
    def test_empty_covers_nothing(self):
        assert ProtectedSpans().covers(0) is False

    def test_covers_within_interval(self):
        spans = ProtectedSpans(((5, 10),))
        assert spans.covers(5) is True
        assert spans.covers(9) is True

    def test_does_not_cover_end_boundary(self):
        # half-open: end is exclusive
        spans = ProtectedSpans(((5, 10),))
        assert spans.covers(10) is False

    def test_does_not_cover_outside_interval(self):
        spans = ProtectedSpans(((5, 10),))
        assert spans.covers(4) is False
        assert spans.covers(11) is False


class TestDetectFencedCode:
    def test_finds_triple_backtick_fence(self):
        text = "before ```code here``` after"
        spans = detect_protected_spans(text)
        start = text.index("```")
        end = text.index("after") - 1
        assert spans.covers(start) is True
        assert spans.covers(end - 1) is True

    def test_finds_tilde_fence(self):
        text = "before ~~~code here~~~ after"
        spans = detect_protected_spans(text)
        start = text.index("~~~")
        assert spans.covers(start) is True

    def test_does_not_protect_outside_fence(self):
        text = "plain text ```code``` more plain text"
        spans = detect_protected_spans(text)
        assert spans.covers(0) is False
        assert spans.covers(len(text) - 1) is False

    def test_multiline_fence(self):
        text = "before\n```\nline one\nline two\n```\nafter"
        spans = detect_protected_spans(text)
        idx = text.index("line one")
        assert spans.covers(idx) is True


class TestDetectInlineCode:
    def test_finds_inline_code(self):
        text = "call `foo.bar()` to proceed"
        spans = detect_protected_spans(text)
        idx = text.index("foo.bar")
        assert spans.covers(idx) is True

    def test_inline_code_does_not_cross_newline(self):
        text = "a `not closed\nstill not code` b"
        spans = detect_protected_spans(text)
        idx = text.index("not closed")
        assert spans.covers(idx) is False


class TestDetectUrls:
    def test_finds_bare_https_url(self):
        text = "see https://example.com/path?q=1 for details"
        spans = detect_protected_spans(text)
        idx = text.index("example.com")
        assert spans.covers(idx) is True

    def test_finds_bare_http_url(self):
        text = "see http://example.com for details"
        spans = detect_protected_spans(text)
        idx = text.index("example.com")
        assert spans.covers(idx) is True

    def test_url_stops_at_whitespace(self):
        text = "https://example.com then text"
        spans = detect_protected_spans(text)
        then_idx = text.index("then")
        assert spans.covers(then_idx) is False

    def test_url_stops_at_closing_paren(self):
        text = "(see https://example.com/x) done"
        spans = detect_protected_spans(text)
        done_idx = text.index("done")
        assert spans.covers(done_idx) is False

    def test_does_not_protect_non_url_text(self):
        text = "no links here at all"
        spans = detect_protected_spans(text)
        assert spans.intervals == ()


class TestDetectMarkdownLinkTargets:
    def test_protects_link_target_url(self):
        text = "read [the docs](https://example.com/docs) now"
        spans = detect_protected_spans(text)
        idx = text.index("example.com")
        assert spans.covers(idx) is True

    def test_link_text_itself_is_not_protected(self):
        # Only the href is protected; visible link text scrubs normally.
        text = "read [the docs](https://example.com/docs) now"
        spans = detect_protected_spans(text)
        link_text_idx = text.index("the docs")
        assert spans.covers(link_text_idx) is False

    def test_ignores_non_url_paren_content(self):
        text = "see [reference](not a url) here"
        spans = detect_protected_spans(text)
        idx = text.index("not a url")
        assert spans.covers(idx) is False


class TestMergeOverlapping:
    def test_adjacent_matches_do_not_duplicate_or_break(self):
        # A markdown link's URL is both an inline URL match and a link-target
        # match -- overlapping spans from different patterns must merge
        # cleanly, not produce inconsistent/duplicate intervals.
        text = "[x](https://example.com/a)"
        spans = detect_protected_spans(text)
        url_idx = text.index("example.com")
        assert spans.covers(url_idx) is True
        # merged intervals are non-overlapping and sorted
        starts = [s for s, _e in spans.intervals]
        assert starts == sorted(starts)
        for (s1, e1), (s2, _e2) in zip(spans.intervals, spans.intervals[1:]):
            assert e1 < s2 or e1 <= s2  # no overlap between consecutive merged spans


class TestProtectedSpansImmutable:
    def test_frozen(self):
        spans = ProtectedSpans()
        import pytest

        with pytest.raises(AttributeError):
            spans.intervals = ((0, 1),)  # type: ignore[misc]
