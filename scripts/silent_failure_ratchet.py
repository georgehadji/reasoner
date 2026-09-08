"""Ratchet for bare-swallow `except Exception` sites under src/reasoner.

docs/plans/root-cause-remediation-2026-09-07.md (P5) measured this by hand as
616 `except Exception` blocks in src/reasoner, 97 of which swallow outright —
body is `pass` or a bare `return`, no log, no re-raise, no record that
anything degraded. Running that check as code here (skipping comment-only
lines when finding the body's first real statement, which the manual
`grep -A1` did not do) finds 117 on the same tree. MAX below is the code's own
count, not the plan's hand count — the two-way ratchet only works against a
number the script itself can reproduce. D11 (NEMOTRON_RERANK_MODEL silently
404ing on every call, forever) is the archetype: the only trace was a DEBUG
log nobody reads.

This does not judge the 519 non-bare sites — a `except Exception as e: log...;
raise` is not counted, deliberately. It counts only the ones with no signal at
all, the same class D11 came from.

Same two-way pattern as ruff_ratchet.py / bandit_ratchet.py /
count_importlinter_exceptions.py: MAX moves in lockstep with the real count in
either direction. Reduce it by routing a site through core/degrade.py's
`degraded()` helper (logs, increments a counter, records to
PipelineState.degradations) or through an existing signal-carrying mechanism
(DegradedLLMResponse, NoopExecutor, the circuit breaker) instead of a bare
pass/return, and lower MAX by the number of sites converted in the same change.

Two things are deliberately NOT counted, both added when the first sites were
converted: lines inside multi-line string literals (core/degrade.py's docstring
shows the very pattern this counts, so documenting the fix raised the number),
and bodies that call ``degraded(...)`` (a converted site still reads
``return ...``, so without the exemption the ratchet punished the fix).

One thing that WAS wrongly not counted, fixed later: a swallow with a trailing
comment (``pass  # best-effort``) did not match the body pattern, so 7 sites
were invisible to a script whose entire job is honest accounting. The count
went up when that was fixed. A number that only ever falls is not a
measurement.

Usage: python scripts/silent_failure_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "reasoner"

_EXCEPT_RE = re.compile(r"^\s*except\s+Exception\b.*:\s*(#.*)?$")
# The trailing-comment group is load-bearing: without it ``pass  # best-effort``
# escaped the count entirely, and a swallow that explains itself in a comment is
# still a swallow -- arguably the more deliberate kind. Fixing this raised the
# real count by 6 sites that had never been counted, plus the one in
# event_emission_service.py converted in the same change.
_SWALLOW_RE = re.compile(r"^(pass|return\b.*?)(\s+#.*)?$")
# ``return degraded("site", fallback, exc=exc, state=state)`` is the sanctioned
# replacement this script exists to drive sites towards -- it logs, increments
# reasoner_degradation_total and records to PipelineState.degradations. Without
# this exemption a converted site still matched the bare-return pattern and the
# count did not move, so the ratchet punished the fix.
_SIGNALLED_RE = re.compile(r"\bdegraded\s*\(")


def _multiline_string_lines(source: str) -> set[int]:
    """1-based line numbers occupied by multi-line string literals.

    Without this, the docstring in core/degrade.py -- which shows the very
    pattern this script asks callers to adopt --

        except Exception as exc:
            return degraded("rerank.nemotron", documents, exc=exc, state=state)

    counts as a swallow site, so documenting the fix raises the number the fix
    is supposed to lower. Single-line strings cannot contain a matching
    two-line pattern, so only multi-line literals are excluded.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    spans: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.end_lineno
            and node.end_lineno > node.lineno
        ):
            spans.update(range(node.lineno, node.end_lineno + 1))
    return spans


def find_swallow_sites(root: Path = SRC) -> list[tuple[Path, int]]:
    sites: list[tuple[Path, int]] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        in_string = _multiline_string_lines(source)
        for i, line in enumerate(lines):
            if not _EXCEPT_RE.match(line) or (i + 1) in in_string:
                continue
            # First non-blank line after the `except` header, ignoring
            # comment-only lines — that is the body's first real statement.
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate or candidate.startswith("#"):
                    continue
                if _SWALLOW_RE.match(candidate) and not _SIGNALLED_RE.search(candidate):
                    sites.append((path, i + 1))
                break
    return sites


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    sites = find_swallow_sites()
    for path, lineno in sites:
        print(f"{path.relative_to(SRC.parent.parent)}:{lineno}: bare except-Exception swallow")

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
