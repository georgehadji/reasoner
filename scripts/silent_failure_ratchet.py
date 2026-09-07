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

Usage: python scripts/silent_failure_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "reasoner"

_EXCEPT_RE = re.compile(r"^\s*except\s+Exception\b.*:\s*(#.*)?$")
_SWALLOW_RE = re.compile(r"^(pass|return\b.*)$")


def find_swallow_sites(root: Path = SRC) -> list[tuple[Path, int]]:
    sites: list[tuple[Path, int]] = []
    for path in sorted(root.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not _EXCEPT_RE.match(line):
                continue
            # First non-blank line after the `except` header, ignoring
            # comment-only lines — that is the body's first real statement.
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate or candidate.startswith("#"):
                    continue
                if _SWALLOW_RE.match(candidate):
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
