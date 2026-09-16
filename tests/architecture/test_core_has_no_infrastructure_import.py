"""`core` reports a degradation; `infrastructure` counts it.

`core.degrade.degraded()` reached `REASONER_DEGRADATION_TOTAL` through a
function-local `from reasoner.infrastructure.metrics import ...`. The comment
above it said the laziness was what kept `core` off `infrastructure` -- it did
not. import-linter reads the static import graph, so a function-local import is
the same edge as a module-level one, and this single line was the whole reason
the Layered Architecture contract had never been green.

The edge is inverted now: `core/ports/metrics_port.py` declares a hook and
`infrastructure/metrics.py` fills it in at import, which is the direction the
layers already allow. These tests cover the two halves that a future refactor
could silently break: the import must stay out of `core`, and the counter must
still be reached once `infrastructure.metrics` is loaded.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "src" / "reasoner" / "core"


def _type_checking_lines(tree: ast.AST) -> set[int]:
    """Lines inside an `if TYPE_CHECKING:` body.

    Excluded for the same reason `.importlinter` sets
    `exclude_type_checking_imports = True`: a type-only import is erased at
    runtime and creates no dependency. `core/protocol.py` has one on
    ProviderRouter and it is fine.
    """
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        name = (
            test.id if isinstance(test, ast.Name)
            else test.attr if isinstance(test, ast.Attribute)
            else None
        )
        if name == "TYPE_CHECKING":
            for stmt in node.body:
                lines.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    return lines


def test_core_imports_no_infrastructure_module_anywhere():
    """Function-local imports count. That is the mistake this replaces."""
    offenders = []
    for path in sorted(CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        type_only = _type_checking_lines(tree)
        for node in ast.walk(tree):
            if getattr(node, "lineno", None) in type_only:
                continue
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = next(
                    (a.name for a in node.names if a.name.startswith("reasoner.infrastructure")),
                    None,
                )
            if module and module.startswith("reasoner.infrastructure"):
                rel = path.relative_to(CORE.parent).as_posix()
                offenders.append(f"{rel}:{node.lineno} -> {module}")

    assert not offenders, (
        "reasoner.core must not import reasoner.infrastructure, at module scope "
        "or inside a function. Invert the edge with a hook in core/ports/ that "
        "the adapter fills in. Found:\n  " + "\n  ".join(offenders)
    )


def test_degradation_is_counted_once_infrastructure_metrics_is_imported():
    """The hook is filled in by importing the adapter, with no wiring step."""
    from reasoner.core.ports import metrics_port

    import reasoner.infrastructure.metrics  # noqa: F401  — fills the hook on import

    assert metrics_port._DEGRADATION_COUNTER is not None

    seen: list[str] = []
    metrics_port.set_degradation_counter(seen.append)
    try:
        from reasoner.core.degrade import degraded

        sentinel = object()
        assert degraded("test.site", sentinel, exc=ValueError("boom")) is sentinel
        assert seen == ["test.site"]
    finally:
        metrics_port.set_degradation_counter(
            lambda site: reasoner.infrastructure.metrics.REASONER_DEGRADATION_TOTAL.labels(
                site=site
            ).inc()
        )


def test_a_broken_counter_never_breaks_the_caller():
    """Metrics are the least important thing happening at a degradation site."""
    from reasoner.core.degrade import degraded
    from reasoner.core.ports import metrics_port

    previous = metrics_port._DEGRADATION_COUNTER

    def _explode(site: str) -> None:
        raise RuntimeError("prometheus is on fire")

    metrics_port.set_degradation_counter(_explode)
    try:
        sentinel = object()
        assert degraded("test.site", sentinel, exc=ValueError("boom")) is sentinel
    finally:
        metrics_port.set_degradation_counter(previous)
