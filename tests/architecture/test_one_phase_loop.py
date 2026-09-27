"""Strategies supply steps. One loop runs them, and one resolver names them.

Every `WorkflowStrategy` used to carry its own `execute()`, and the SSE driver
at `api/execution/pipeline.py` never called a single one of them: it built a
flat list from `get_phases()` and drove the phase functions itself. So whatever
a strategy held in `execute()` ran for CLI users and not for web users.
`WritingFlow` held a billable augmentation pass there; `DelphiFlow` held the
converged-dissent skip; `article.py` had already discovered the same thing and
left the finding in a comment. Seven of the 21 also dropped the `step.critical`
check, which is why `jury.py`'s critical "Critic Pool" was fatal on the web and
non-fatal on the CLI.

Each of those is covered behaviourally in `tests/test_flows_one_loop.py`. This
file covers the shape, because the next strategy to reintroduce an `execute()`
would reopen the split silently and every behavioural test would still pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reasoner"
FLOWS = SRC / "application" / "flows"


def _defs_named(path: Path, name: str) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                found.append((f"{node.name}.{item.name}", item.lineno))
    return found


def test_no_strategy_defines_execute():
    """A strategy that runs its own loop is reachable from one driver only."""
    offenders = []
    for path in sorted(FLOWS.rglob("*.py")):
        for qualname, lineno in _defs_named(path, "execute"):
            offenders.append(f"{path.relative_to(SRC).as_posix()}:{lineno} {qualname}")

    assert not offenders, (
        "WorkflowStrategy subclasses must supply steps, not a loop. "
        "WorkflowRunner.run is the Template Method; put shared work in a "
        "PhaseStep so both drivers run it. Found:\n  " + "\n  ".join(offenders)
    )


def test_only_the_runner_executes_a_phase_function():
    """Reading `step.fn` to await it is what "one execution engine" means.

    `api/execution/pipeline.py` held a second phase loop with its own retries,
    timeouts, quality gate and fatality rule, so every question about how a
    phase runs had two answers. It is gone; the SSE-specific parts of it are a
    `PhaseObserver` on the runner.

    The one survivor is not a rival loop: `flows/services.py` holds the single
    bare `await step.fn(...)` that `PipelineWorkflowServices` falls back to
    when it was built without a runner, which is what
    `WORKFLOW_RUNNER_ENABLED=false` selects. It retires with that flag.
    (`flows/pipeline_flow.execute_phases_dag` was the third; 78e6e48 deleted
    it as dead.)

    Only reads count -- `PhaseStep.__init__`'s `self.fn = fn` is the field
    itself.
    """
    readers = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "fn"
                and isinstance(node.ctx, ast.Load)
            ):
                readers.add(path.relative_to(SRC).as_posix())

    assert sorted(readers) == [
        "application/flows/runner.py",
        "application/flows/services.py",
    ], f"a second thing executes phases: {sorted(readers)}"


def test_reasoner_pipeline_holds_no_phase_delegators():
    """A phase belongs to its flow module, not to a method that forwards to it.

    The mixin-cleanup refactor (c7f3104) moved phase logic to standalone
    `(state, services)` functions but left 33 two-line delegators on
    `ReasonerPipeline` because its callers were never migrated -- so the tests
    and `api/routes/context.py` went on calling bound methods, and the class
    stayed the apparent owner of phases it no longer implemented. Phase B-3
    migrated the callers and deleted the delegators.

    A delegator here is a method whose entire body is a local import of a flow
    function plus a call to it.
    """
    pipeline = SRC / "application" / "pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [s for s in item.body if not _is_docstring(s)]
            if len(body) != 2:
                continue
            imp, call = body
            if not (
                isinstance(imp, ast.ImportFrom)
                and (imp.module or "").startswith("reasoner.application.flows")
            ):
                continue
            inner = call.value if isinstance(call, (ast.Expr, ast.Return)) else None
            if isinstance(inner, ast.Await):
                inner = inner.value
            if isinstance(inner, ast.Call):
                offenders.append(f"{item.lineno} {node.name}.{item.name}")

    assert not offenders, (
        "ReasonerPipeline must not forward to flow functions; call them "
        "directly with a PipelineWorkflowServices. Found:\n  " + "\n  ".join(offenders)
    )


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def test_get_phases_has_exactly_one_caller():
    """One resolver builds the phase list, so the drivers cannot disagree.

    They did disagree: the SSE driver appended the Layer B egress rewrite and
    the CLI did not, so that phase never applied to a CLI, headless or MCP run.
    """
    callers = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_phases"
            ):
                callers.add(path.relative_to(SRC).as_posix())

    assert sorted(callers) == ["application/flows/runner.py"], (
        "resolve_phases() must be the only caller of get_phases(); any other "
        "caller is a second phase list that can drift from it. Found: " + str(callers)
    )
