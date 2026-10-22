"""Every HTTP route that runs a pipeline goes through admit_run and metered().

``/api/run-with-context`` and the resume stream ran paid pipelines without
either (docs/plans/audit-remediation-2-2026-10-20.md BIL-10, BIL-11). This scans
the route functions' source, so a new route that starts a run without the
admission sequence fails here instead of in production.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

API_DIR = Path(__file__).resolve().parents[2] / "src" / "reasoner" / "api"

#: Names whose use means the route runs a billed pipeline.
RUNS_A_PIPELINE = frozenset({
    "run_stream",
    "run_stream_cached",
    "run_followup_stream",
    "_run_stream_with_metrics",
    "_run_followup_stream_with_metrics",
    "_metered_agent_stream",
    "run_synthesis_phase",
})
#: ``metered()`` itself, or a module helper that wraps the stream in it.
METERS = frozenset({
    "metered",
    "_run_stream_with_metrics",
    "_run_followup_stream_with_metrics",
    "_metered_agent_stream",
})


def _names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def _is_route(func: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr in {"post", "get", "put", "patch", "delete"}
        for d in func.decorator_list
    )


def _pipeline_routes() -> list[tuple[str, str, set[str]]]:
    routes = []
    for path in sorted(API_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef)) and _is_route(func):
                names = _names(func)
                if names & RUNS_A_PIPELINE:
                    routes.append((path.relative_to(API_DIR).as_posix(), func.name, names))
    return routes


def test_the_scan_finds_the_known_run_routes():
    found = {name for _, name, _ in _pipeline_routes()}
    assert {
        "run_pipeline", "run_followup_pipeline", "agent_run", "agent_run_sync",
        "run_with_context", "resume_pipeline_stream",
    } <= found, found


@pytest.mark.parametrize(
    "module,route,names", _pipeline_routes(), ids=lambda v: v if isinstance(v, str) else "",
)
def test_every_pipeline_route_is_admitted_and_metered(module, route, names):
    assert "admit_run" in names, f"{module}::{route} runs a pipeline without admit_run()"
    assert names & METERS, f"{module}::{route} runs a pipeline outside metered()"
