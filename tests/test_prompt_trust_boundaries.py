"""Untrusted text reaches a prompt only through a wrapper.

Invariant 4 of CLAUDE.md §5 ("model- or web-authored text is wrapped, never
interpolated raw") held by omission, so refactors broke it silently: context
vetting, decomposition, fusion and a dozen inter-phase prompts all
interpolated raw text (docs/plans/audit-remediation-2-2026-10-20.md SEC-9,
SEC-11, SEC-13, SEC-14). This scan makes the omission a failing test.

It walks every f-string in ``phases/`` and ``subagents/``. An interpolated
expression that reads a known untrusted field must be a call to one of the
wrappers. Justified exceptions live in ``ALLOWED`` with a reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[1] / "src" / "reasoner"
SCANNED = [SRC / "phases", SRC / "subagents"]

#: Attribute names, subscript keys and variable names that hold user-, web- or
#: model-authored text.
UNTRUSTED = frozenset({
    "problem", "enhanced_problem", "web_discovery_results", "vetted_context",
    "candidates", "content", "snippet", "text", "previous_synthesis",
})
#: Calls whose result is safe to interpolate.
WRAPPERS = frozenset({
    "_wrap_external_content", "_wrap_user_input", "build_web_sources_block",
    "build_memory_context", "build_followup_context", "_followup_context",
})
#: (module path relative to src/reasoner, function, field) -> reason.
ALLOWED: dict[tuple[str, str, str], str] = {
    ("phases/_shared.py", "build_synthesis_context", "snippet"):
        "the whole block is wrapped by synthesis_prompt(); see the comment at the site",
    ("phases/coding.py", "coding_review_prompt", "snippet"):
        "joined into cve_context, which is wrapped as one block",
    ("phases/coding.py", "coding_assemble_prompt", "content"):
        "prints len(content), not the content",
    ("phases/multi_perspective.py", "perspective_prompt", "text"):
        "joined into premises_block, which is wrapped as one block",
    ("subagents/base.py", "_cache_key", "problem"):
        "a cache key, never sent to a model",
    ("subagents/enhancement/hyper_agent.py", "execute", "problem"):
        "builds enhanced_problem, which is wrapped where it is prompted",
}


def _reads(expr: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(expr):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                names.add(node.slice.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and node.args and isinstance(node.args[0], ast.Constant):
                names.add(str(node.args[0].value))
    return names


def _is_wrapped(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Call):
        func = expr.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return name in WRAPPERS
    return False


def _violations(allowed=ALLOWED) -> list[tuple[str, str, str, int]]:
    found = []
    for root in SCANNED:
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(SRC).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if func.name in WRAPPERS:
                    continue  # the wrappers' own bodies interpolate by definition
                # An f-string passed to a wrapper is wrapped as a whole.
                inside_wrapper = {
                    id(sub)
                    for call in ast.walk(func) if _is_wrapped(call)
                    for arg in call.args for sub in ast.walk(arg)
                }
                for node in ast.walk(func):
                    if not isinstance(node, ast.JoinedStr) or id(node) in inside_wrapper:
                        continue
                    for part in node.values:
                        if not isinstance(part, ast.FormattedValue) or _is_wrapped(part.value):
                            continue
                        for field in sorted(_reads(part.value) & UNTRUSTED):
                            if (rel, func.name, field) not in allowed:
                                found.append((rel, func.name, field, part.lineno))
    return found


def test_scan_sees_the_prompt_modules():
    assert any(SRC.joinpath("phases").rglob("*.py"))
    assert any(SRC.joinpath("subagents").rglob("*.py"))


def test_no_untrusted_field_is_interpolated_raw():
    bad = _violations()
    header = "Raw untrusted interpolation (wrap it, or add to ALLOWED with a reason):\n"
    assert not bad, header + "\n".join(
        f"  {rel}:{line} {func}() reads {field}" for rel, func, field, line in bad
    )


def test_allowlist_has_no_stale_entries():
    live = {(rel, func, field) for rel, func, field, _ in _violations(allowed={})}
    stale = set(ALLOWED) - live
    assert not stale, f"ALLOWED entries no longer needed: {sorted(stale)}"
