"""T6 defect-hunt: extract_json must not rewrite the *contents* of string values.

D1 (VERIFIED, fixed): ``_strip_trailing_commas`` ran ``re.sub(r',\\s*([}\\]])')``
over the whole response, including inside string literals, and did so *before*
the first strict parse attempt. Any model answer whose text contained a comma
followed by whitespace and a ``}``/``]`` — a code snippet, an embedded JSON
example, ordinary prose — came back silently altered. No exception, no log.

D2 (VERIFIED, NOT fixed — see docs/reports/defect-hunt-2026-09-01/T6-parsing-state.md):
bare ``NaN``/``Infinity`` survive the parse as non-finite floats, which
``safe_float`` then clamps to the *maximum* bound (10.0) instead of the default.
The single-chokepoint fix lives in ``reasoner.utils.json_safe.safe_json_loads``,
outside the T6 surface, so it is escalated rather than applied here.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from reasoner.core.parsing import extract_json, safe_float


# ── D1 proof-of-defect (fails without the fix) ──────────────────────────────

@pytest.mark.parametrize(
    "value",
    [
        "items = [1, 2, ]",
        "Choose A, B, or C, } is the closing token.",
        'schema is {"x": 1, } — note the trailing comma',
        "a, ] b, } c",
    ],
    ids=["array-literal", "prose-brace", "embedded-json", "both-delimiters"],
)
def test_string_values_survive_trailing_comma_repair(value: str) -> None:
    """A comma inside a string value is data, not JSON syntax."""
    payload = json.dumps({"content": value})
    assert extract_json(payload)["content"] == value


# ── Boundary cases ──────────────────────────────────────────────────────────

def test_empty_and_blank_input_still_yield_empty_dict() -> None:
    assert extract_json("") == {}
    assert extract_json("   \n\t ") == {}


def test_string_that_is_only_a_delimiter_sequence() -> None:
    payload = json.dumps({"k": ", }"})
    assert extract_json(payload)["k"] == ", }"


def test_escaped_quote_inside_value_does_not_desynchronise_the_scanner() -> None:
    """An escaped quote must not be read as the end of the string literal."""
    value = 'he said \\"go, ]\\" then left'
    payload = '{"a": "he said \\"go, ]\\" then left", "b": [1, 2, ],}'
    result = extract_json(payload)
    assert result["a"] == value.replace("\\", "")
    assert result["b"] == [1, 2]


# ── D3 proof-of-defect: truncation repair must precede the array fallback ──

def test_truncated_object_keeps_its_keys_not_just_an_inner_array() -> None:
    """A token-limit cutoff mid-object used to return only the inner array.

    ``_repair_truncated_json`` sat *after* the array fallback, so a response cut
    mid-object whose inner array was complete matched the array branch first and
    came back as ``{"results": [...]}`` — every named key silently discarded.
    """
    result = extract_json(
        '{"core_solution": "long text", "critical_insights": ["x", "y"], '
        '"action_blueprint": ["do a"], "open_q'
    )
    assert result["core_solution"] == "long text"
    assert result["critical_insights"] == ["x", "y"]
    assert "results" not in result


def test_unterminated_final_string_still_repairs_structure() -> None:
    """Truncated output: the tail is treated as non-string, so repair still runs."""
    result = extract_json('{"a": 1, "b": [1, 2, ], "c": "cut off her')
    assert result["a"] == 1
    assert result["b"] == [1, 2]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[1, 2, 3]", {"results": [1, 2, 3]}),
        ("[]", {"results": []}),
        ('{"items": ["one", "two", "thr', {"items": ["one", "two"]}),
    ],
    ids=["root-array", "empty-array", "truncated-array"],
)
def test_array_roots_still_reach_the_array_fallback(raw: str, expected: dict) -> None:
    """No-regression: reordering must not steal genuinely array-rooted responses."""
    assert extract_json(raw) == expected


# ── No-regression: real trailing commas are still removed ───────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1, "b": [1, 2, ],}', {"a": 1, "b": [1, 2]}),
        ('{"a": 1,}', {"a": 1}),
        ('{\n  "a": [\n    1,\n    2,\n  ],\n}', {"a": [1, 2]}),
        ('```json\n{"a": 1, "b": 2,}\n```', {"a": 1, "b": 2}),
        ("Here you go:\n{'x': 1}\n{\"a\": 1,}", {"a": 1}),
    ],
    ids=["nested", "flat", "multiline", "fenced", "prose-preamble"],
)
def test_structural_trailing_commas_are_still_stripped(raw: str, expected: dict) -> None:
    assert extract_json(raw) == expected


@settings(max_examples=200, deadline=None)
@given(st.dictionaries(st.text(min_size=1, max_size=12), st.text(max_size=200), max_size=6))
def test_any_valid_json_object_round_trips_unchanged(payload: dict[str, str]) -> None:
    """Property: extract_json is the identity on well-formed JSON objects."""
    assert extract_json(json.dumps(payload)) == payload


# ── D2: confirmed, unfixed (chokepoint outside the T6 surface) ─────────────

@pytest.mark.xfail(
    reason="VERIFIED DEFECT, escalated: bare NaN/Infinity survive extract_json. "
           "Fix belongs in reasoner.utils.json_safe.safe_json_loads (parse_constant), "
           "outside the T6 file surface.",
    strict=True,
)
def test_non_finite_json_constants_are_rejected() -> None:
    parsed = extract_json('{"logical_consistency": NaN, "feasibility": Infinity}')
    json.dumps(parsed, allow_nan=False)  # raises ValueError today


def test_safe_float_clamps_nan_to_the_upper_bound_not_the_default() -> None:
    """Documents the damaging consequence of D2: NaN reads as a perfect score."""
    assert safe_float(float("nan")) == 10.0  # not 0.0 — the reason D2 matters
