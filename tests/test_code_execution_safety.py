"""Regression tests for the generated-code execution containment guard."""

from __future__ import annotations

from reasoner.core.code_safety import CodeSafetyError, check_code_safety


def test_filesystem_imports_are_blocked() -> None:
    for source in (
        "from pathlib import Path\nPath('secret').read_text()",
        "from pathlib import Path\nPath('secret').write_text('x')",
        "import io\nio.open('secret')",
    ):
        try:
            check_code_safety(source)
        except CodeSafetyError:
            continue
        raise AssertionError("filesystem access must be rejected")


def test_pickle_deserialization_is_blocked() -> None:
    try:
        check_code_safety("import pickle\npickle.loads(b'payload')")
    except CodeSafetyError:
        return
    raise AssertionError("pickle deserialization must be rejected")
