"""Safe JSON loading with depth limits to prevent stack exhaustion."""

from __future__ import annotations

import json
from typing import Any


class JSONDepthExceededError(ValueError):
    """Raised when JSON nesting exceeds the configured maximum depth."""


def _check_depth(obj: Any, current_depth: int, max_depth: int) -> None:
    """Recursively check nesting depth of parsed JSON object."""
    if current_depth > max_depth:
        raise JSONDepthExceededError(f"JSON depth {current_depth} exceeds maximum {max_depth}")
    if isinstance(obj, dict):
        for v in obj.values():
            _check_depth(v, current_depth + 1, max_depth)
    elif isinstance(obj, list):
        for item in obj:
            _check_depth(item, current_depth + 1, max_depth)


def _reject_non_finite(constant: str) -> Any:
    """Reject the three bare constants Python's json accepts but JSON does not.

    stdlib json parses NaN, Infinity and -Infinity by default. Model output is
    not trusted input, and a non-finite score is worse than a rejected one:
    safe_float() returned max_val (10.0) rather than its 0.0 default for NaN,
    because every comparison against NaN is False, so a malformed response read
    as a perfect score instead of a discarded one.

    Raises JSONDecodeError, not a bare ValueError, so callers treat this exactly
    as they already treat malformed JSON: reasoner.core.parsing's strategies
    each catch JSONDecodeError to fall through, and raise ParseError once all
    of them fail. A new exception type would escape that chain uncaught.
    """
    raise json.JSONDecodeError(
        f"non-finite JSON constant is not accepted: {constant}", constant, 0
    )


def safe_json_loads(data: str | bytes, max_depth: int = 100) -> Any:
    """Parse JSON with a strict depth limit, rejecting non-finite constants.

    Args:
        data: JSON string or bytes.
        max_depth: Maximum allowed nesting depth (default 100).

    Raises:
        JSONDepthExceededError: If parsed structure exceeds *max_depth*.
        json.JSONDecodeError: If *data* is not valid JSON, or contains bare
            NaN, Infinity or -Infinity.
    """
    parsed = json.loads(data, parse_constant=_reject_non_finite)
    _check_depth(parsed, 1, max_depth)
    return parsed
