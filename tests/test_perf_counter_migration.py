"""Tests ensuring latency paths use perf_counter, not time.time."""

from __future__ import annotations

import ast
from pathlib import Path


LATENCY_FILES = [
    Path("src/reasoner/infrastructure/llm/ports.py"),
    Path("src/reasoner/neuro/server.py"),
    Path("src/reasoner/infrastructure/widgets/protocol.py"),
]


def test_no_time_time_in_latency_paths():
    """
    Verify that latency measurement paths do not use time.time().
    """
    for filepath in LATENCY_FILES:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "time"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "time"
                ):
                    # Found time.time() call — fail
                    raise AssertionError(
                        f"Found time.time() in {filepath}; use time.perf_counter() for latency"
                    )
