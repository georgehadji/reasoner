"""Every function in ``api/`` that calls a paid provider goes through admission.

BIL-26 (docs/plans/audit-remediation-5-2026-10-29.md): search, image preview
and the gate called paid providers with no credit check, because nothing
forced a new route to reserve. This scan fails when a function calls one of
the paid entry points without also calling an admission step.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

API_DIR = Path(__file__).resolve().parents[2] / "src" / "reasoner" / "api"

PAID = {"smart_search", "enhance_image_prompt", "generate_images", "decide_route", "save_uploaded_file"}
#: ``search_service.search(...)`` -- the attribute alone would match ``re.search``.
PAID_METHODS = {("search_service", "search")}
ADMISSION = {"admit_run", "admit_flat_charge", "_admit_mcp_caller", "within_gate_allowance"}


def _called(fn: ast.AST) -> tuple[set[str], set[tuple[str, str]]]:
    names: set[str] = set()
    methods: set[tuple[str, str]] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
            if isinstance(func.value, ast.Name):
                methods.add((func.value.id, func.attr))
    return names, methods


def test_paid_calls_are_admitted() -> None:
    offenders = []
    scanned = 0
    for path in sorted(API_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            names, methods = _called(fn)
            if not (names & PAID or methods & PAID_METHODS):
                continue
            scanned += 1
            if not names & ADMISSION:
                offenders.append(f"{path.relative_to(API_DIR)}::{fn.name}")

    assert scanned, "found no paid calls in api/ -- the scan itself is broken"
    assert not offenders, f"paid provider calls with no admission step: {offenders}"
