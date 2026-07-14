"""Tests for referential follow-up detection."""

from __future__ import annotations

import pytest

from reasoner.phases._shared import is_referential_followup


@pytest.mark.parametrize(
    "problem,history,expected",
    [
        ("Continue", [{"role": "assistant", "content": "prev"}], True),
        ("Expand on that", [{"role": "assistant", "content": "prev"}], True),
        ("Elaborate", [{"role": "assistant", "content": "prev"}], True),
        ("Add more details", [{"role": "assistant", "content": "prev"}], True),
        ("New topic", [{"role": "assistant", "content": "prev"}], False),
        ("Continue", [], False),
    ],
)
def test_is_referential_followup(problem, history, expected):
    assert is_referential_followup(problem, history) is expected
