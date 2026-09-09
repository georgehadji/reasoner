"""Ratchet for signal-free `except Exception` sites under src/reasoner.

docs/plans/root-cause-remediation-2026-09-07.md (P5) measured this by hand as
616 `except Exception` blocks in src/reasoner, 97 of which swallow outright —
body is `pass` or a bare `return`, no log, no re-raise, no record that
anything degraded. D11 (NEMOTRON_RERANK_MODEL silently 404ing on every call,
forever) is the archetype: the only trace was a DEBUG log nobody reads.

That last sentence is why this script no longer looks for `pass` and `return`.
It used to, with a line regex over the handler's first statement, and D11's own
shape — a handler whose whole body is `logger.debug(...)` and which then falls
through returning `None` — did not match it. So the check could not see the
archetype it was written for. `infrastructure/llm/executor.py:756`, the handler
wrapping spend-cap enforcement, sat uncounted at every MAX for the same reason
until it was found by hand (docs/plans/implementation_audit_report.md, C-1).

Switching to the AST below raised the real count 58 -> 105. Those 47 sites had
never once been counted, and they came from three separate blind spots in the
text scan, not one:

  * ``except (asyncio.CancelledError, Exception): pass`` -- a tuple, so the
    regex, which required ``Exception`` as the first token after ``except``,
    never matched (api/phase_executor.py:107).
  * ``except Exception: return []`` on a single line -- the scan read the
    handler's body from the *next* line (application/flows/debate.py:41).
  * ``logger.debug(...)`` followed by ``return False`` -- D11's own shape. The
    scan tested only the first statement, saw a call, and stopped
    (infrastructure/valkey/state_adapter.py:28).

docs/plans/audit-remediation-2026-09-08.md R1 predicted 80 from an ad-hoc
measurement that covered only the third of those. The number here is the
measured one; the prediction was low.

A handler counts here when ALL of:

  * it catches ``Exception`` (alone or inside a tuple),
  * every statement in its body is `pass`, a `return`, or a logging call
    below WARNING,
  * and nothing in that body calls ``degraded(...)``.

Re-raising needs no clause of its own: ``raise`` is a statement, so a body that
satisfies the second condition cannot contain one.

The last clause draws the contract's line. ``logger.warning`` /
``logger.error`` / ``logger.exception`` leave a trace at a level someone
alerts on, so a handler containing one is not counted, deliberately — as is a
handler that re-raises, or one already routed through ``degraded()``. This
counts only handlers that leave no signal at all.

Same two-way pattern as ruff_ratchet.py / bandit_ratchet.py /
count_importlinter_exceptions.py: MAX moves in lockstep with the real count in
either direction. Reduce it by routing a site through core/degrade.py's
`degraded()` helper (logs at WARNING, increments reasoner_degradation_total,
records to PipelineState.degradations) or through an existing signal-carrying
mechanism (DegradedLLMResponse, NoopExecutor, the circuit breaker), and lower
MAX by the number of sites converted in the same change.

Two notes carried over from the regex version, both still true:

The AST replaces the old `_multiline_string_lines` guard for free. core/degrade.py's
docstring shows the very pattern this script asks callers to adopt, and under a
text scan documenting the fix raised the number the fix is supposed to lower.
A parser does not read docstrings as code.

A swallow with a trailing comment (``pass  # best-effort``) was invisible to
the regex for a while, so 7 sites went uncounted by a script whose entire job
is honest accounting. The count went up when that was fixed, and it went up
again here. A number that only ever falls is not a measurement.

Usage: python scripts/silent_failure_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "reasoner"

# Below WARNING. A handler whose only trace is one of these is the D11 shape:
# technically logged, operationally silent.
_QUIET_LOG_LEVELS = frozenset({"debug", "info"})


def _catches_exception(handler: ast.ExceptHandler) -> bool:
    """True for ``except Exception`` and ``except (Exception, X)``.

    A bare ``except:`` is a different and much rarer shape; it is left alone
    here rather than folded in silently, so that this count keeps meaning the
    same thing it meant before the AST switch.
    """
    caught = handler.type
    if caught is None:
        return False
    parts = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(isinstance(p, ast.Name) and p.id == "Exception" for p in parts)


def _receiver_name(func: ast.Attribute) -> str:
    """Best-effort name of whatever ``func``'s attribute is being read from."""
    target = func.value
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _is_quiet_log(stmt: ast.stmt) -> bool:
    """``logger.debug(...)`` / ``self.log.info(...)`` as a standalone statement.

    The receiver has to look like a logger. Without that check any
    ``cache.info()`` or ``parser.debug()`` would read as logging and quietly
    exempt a handler that logs nothing at all.
    """
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    if not isinstance(func, ast.Attribute) or func.attr not in _QUIET_LOG_LEVELS:
        return False
    return "log" in _receiver_name(func).lower()


def _calls_degraded(stmt: ast.stmt) -> bool:
    """``return degraded("site", fallback, exc=exc, state=state)`` — the fix.

    A converted site still reads as a bare ``return``, so without this the
    ratchet counts the sanctioned conversion and the number does not move: the
    check punishes the change it exists to drive.
    """
    for node in ast.walk(stmt):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "degraded":
                return True
    return False


def _leaves_no_signal(handler: ast.ExceptHandler) -> bool:
    body = handler.body
    if not all(
        isinstance(stmt, (ast.Pass, ast.Return)) or _is_quiet_log(stmt) for stmt in body
    ):
        return False
    # Re-raising needs no separate check. ``raise`` is a statement, so a handler
    # that survives the shape test above cannot contain one — the only way to
    # smuggle a Raise past it is inside a nested def, and a nested def is itself
    # a statement the shape test rejects. Scanning for it anyway would mean
    # walking into those nested scopes, where a raise belongs to a different
    # handler entirely.
    return not any(_calls_degraded(stmt) for stmt in body)


def find_swallow_sites(root: Path = SRC) -> list[tuple[Path, int]]:
    sites: list[tuple[Path, int]] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and _catches_exception(node)
                and _leaves_no_signal(node)
            ):
                sites.append((path, node.lineno))
    return sorted(sites)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    sites = find_swallow_sites()
    for path, lineno in sites:
        print(f"{path.relative_to(SRC.parent.parent)}:{lineno}: except-Exception leaves no signal")

    count = len(sites)
    print(f"\nsilent-failure sites: {count}")

    if count > args.max:
        print(f"FAIL: {count} sites exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} sites is below ratchet MAX={args.max} — "
            f"debt was paid down; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} sites matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
