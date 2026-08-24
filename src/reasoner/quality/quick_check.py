"""
Fast Quality Gate for Cascading Responses

Lightweight, rule-based quality checks that run *before* accepting a
cascading model response. No LLM calls — pure heuristics for fail-fast.

Design Pattern: Strategy (pluggable quality checks)
"""

from __future__ import annotations

import json
from typing import ClassVar


class QuickQualityCheck:
    """Fast, rule-based quality gate for cascading decisions.

    All methods are static and stateless. They return (passed, reason)
    so the caller can decide whether to cascade to the next model.
    """

    # Minimum response length (in characters) per role
    _MIN_LENGTHS: ClassVar[dict[str, int]] = {
        "synthesis": 200,
        "perspective": 100,
        "article_synthesize": 500,
        "writing_draft": 500,
        "coding_generate": 100,
        "coding_spec": 50,
        "primary": 20,
    }

    # Required top-level keys for JSON roles
    _REQUIRED_JSON_KEYS: ClassVar[dict[str, list[str]]] = {
        "classification": ["task_type"],
        "decomposition": ["sub_problems"],
        "scoring": ["scores"],
        "fusion": ["task_type", "sub_problems"],
    }

    # Roles that are expected to emit valid JSON
    _JSON_ROLES: ClassVar[frozenset[str]] = frozenset(
        ("fusion", "classification", "decomposition", "scoring", "meta_evaluator")
    )

    @classmethod
    def check_json_role(cls, role: str, response: str) -> tuple[bool, str]:
        """Validate JSON structure for roles that require it.

        Returns:
            (passed: bool, reason: str)
        """
        if role not in cls._JSON_ROLES:
            return True, "not a JSON role"

        stripped = response.strip()
        if not stripped:
            return False, "empty response for JSON role"

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return False, f"invalid JSON: {exc}"

        if not isinstance(data, dict):
            return False, "JSON root is not an object"

        required = cls._REQUIRED_JSON_KEYS.get(role, [])
        missing = [k for k in required if k not in data]
        if missing:
            return False, f"missing required keys: {', '.join(missing)}"

        return True, "valid JSON with required keys"

    @classmethod
    def check_content_quality(cls, role: str, response: str) -> tuple[bool, str]:
        """Check for empty, too-short, or repetitive responses.

        Returns:
            (passed: bool, reason: str)
        """
        stripped = response.strip()
        if not stripped:
            return False, "empty response"

        # Length check
        min_len = cls._MIN_LENGTHS.get(role, 20)
        if len(stripped) < min_len:
            return False, f"response too short ({len(stripped)} < {min_len})"

        # Repetition check: if >70% of lines are identical, likely looped
        lines = stripped.splitlines()
        if len(lines) > 5:
            unique_lines = set(lines)
            uniqueness_ratio = len(unique_lines) / len(lines)
            if uniqueness_ratio < 0.3:
                return False, "excessive repetition detected"

        # Markdown fence balance check (for code-heavy roles)
        if role in ("coding_generate", "coding_assemble", "coding_tests"):
            fence_count = stripped.count("```")
            if fence_count % 2 != 0:
                return False, "unbalanced code fences"

        return True, "content quality OK"

    @classmethod
    def check_all(cls, role: str, response: str) -> tuple[bool, str]:
        """Run all quality checks and return the first failure.

        Returns:
            (passed: bool, reason: str)
        """
        ok, reason = cls.check_json_role(role, response)
        if not ok:
            return False, reason

        ok, reason = cls.check_content_quality(role, response)
        if not ok:
            return False, reason

        return True, "all checks passed"
