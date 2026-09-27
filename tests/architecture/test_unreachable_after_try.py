"""No statement may sit after a `try` that every branch already leaves.

`api/execution/pipeline.py` carried the whole per-phase quality gate directly
after a `try` whose body ended in `break` and whose two handlers ended in
`break`. Nothing could reach it, and it stayed that way through every green
run: the enclosing `for retry_attempt` loop is exercised on real traffic, so
line coverage of the loop looked healthy while eleven statements inside it were
dead. Coverage measures lines that ran, not lines that *could* run, so it is
structurally blind to this and a behavioural test only catches the one instance
someone already suspected.

`tests/test_phase_quality_gate.py` covers that instance. This file covers the
class, over all of `src/reasoner`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reasoner"

_TERMINATORS = (ast.Break, ast.Continue, ast.Return, ast.Raise)


def _terminates(body: list[ast.stmt]) -> bool:
    """True when control cannot fall off the end of ``body``.

    Only the last statement matters: anything before it that terminates would
    make its own successors unreachable, which is a different (and rarer)
    defect that Python's own linters already flag.
    """
    if not body:
        return False
    last = body[-1]
    if isinstance(last, _TERMINATORS):
        return True
    if isinstance(last, ast.If):
        return bool(last.orelse) and _terminates(last.body) and _terminates(last.orelse)
    if isinstance(last, ast.Try):
        return _falls_through(last) is False
    if isinstance(last, ast.With):
        return _terminates(last.body)
    return False


def _falls_through(node: ast.Try) -> bool:
    """True when execution can continue past ``node`` to its next sibling."""
    # `else` runs only when the body completed, so the normal path escapes the
    # statement only if both complete.
    normal = not _terminates(node.body) and (
        not node.orelse or not _terminates(node.orelse)
    )
    handled = any(not _terminates(h.body) for h in node.handlers)
    # A `finally` that terminates overrides everything, but that is a separate
    # smell; treat it as falling through so this check reports only the shape it
    # is named for.
    return normal or handled


def _dead_statements(tree: ast.AST) -> list[tuple[int, int]]:
    """(try_lineno, first_dead_lineno) for every unreachable-after-try site."""
    found: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block[:-1]):
                if isinstance(stmt, ast.Try) and not _falls_through(stmt):
                    found.append((stmt.lineno, block[i + 1].lineno))
    return found


def test_no_statement_follows_an_exhausted_try():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for try_line, dead_line in _dead_statements(tree):
            offenders.append(
                f"{path.relative_to(SRC.parent.parent)}:{dead_line} is unreachable "
                f"— the try at :{try_line} leaves on every branch"
            )
    assert offenders == [], "\n".join(offenders)


def test_the_detector_sees_the_shape_it_was_written_for():
    """The exact `api/execution/pipeline.py` defect, reduced."""
    tree = ast.parse(
        "for i in range(2):\n"
        "    try:\n"
        "        work()\n"
        "        break\n"
        "    except TimeoutError:\n"
        "        break\n"
        "    except Exception:\n"
        "        break\n"
        "    gate()\n"
    )
    assert _dead_statements(tree) == [(2, 9)]


def test_a_handler_that_falls_through_keeps_the_next_statement_alive():
    """The fixed shape: `else` carries the continuation, handlers still break."""
    tree = ast.parse(
        "for i in range(2):\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        break\n"
        "    else:\n"
        "        gate()\n"
        "    tail()\n"
    )
    assert _dead_statements(tree) == []
