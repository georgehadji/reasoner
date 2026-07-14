"""Tests for article request detection."""

from __future__ import annotations

import pytest

from reasoner.phases._shared import is_article_request


@pytest.mark.parametrize(
    "problem,expected",
    [
        ("Write an article about climate change", True),
        ("Draft a blog post on Python", True),
        ("Compose a report about sales", True),
        ("What is the capital of France?", False),
        ("Explain quantum computing", False),
    ],
)
def test_is_article_request(problem: str, expected: bool):
    assert is_article_request(problem) is expected
