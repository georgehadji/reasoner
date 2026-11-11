"""Audit: the HTML-to-markdown step kept the page body.

HTML_TAGS_TO_MARKDOWN listed `">` as a key (twice), so the end of any quoted
attribute lost its `>`; the tag-stripping regex then ran on to the next real `>`
and deleted the text in between. A normal page came back as just its title.
"""

from __future__ import annotations

import pytest

from reasoner.infrastructure.scraper import _simple_html_to_markdown

pytestmark = pytest.mark.unit


def test_body_text_survives_tags_with_attributes():
    html = (
        '<html><head><title>T</title></head><body>'
        '<nav class="menu"><a href="/a">Home</a></nav>'
        '<article class="post"><h1>Heading</h1><p>First paragraph.</p>'
        '<p>Second paragraph.</p></article><footer class="f">bye</footer></body></html>'
    )

    text = _simple_html_to_markdown(html)

    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "# Heading" in text
    assert "bye" in text


def test_a_section_with_an_id_is_not_swallowed():
    text = _simple_html_to_markdown('<section id="s"><h2>Title</h2><p>Body text</p></section>')

    assert "Body text" in text


def test_links_become_markdown():
    text = _simple_html_to_markdown('<p>See <a href="http://x.com" class="l">the docs</a> now</p>')

    assert "[the docs](http://x.com)" in text
