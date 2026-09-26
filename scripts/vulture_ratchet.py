"""Ratchet for dead code in src/ (P-5, docs/plans/phaseoutput-retirement-2026-09-12.md).

The case that motivated it: `apply_to` had no caller in src/, only a test
calling it by name, and an import-graph check could not see that. vulture is
given src/ alone, so tests are not reachability roots -- a symbol whose only
caller is a test counts as dead, which is the point.

"unused variable" findings are not counted. Most are FastAPI dependency
parameters (`authenticated: bool = Depends(...)`), which the framework
injects and vulture cannot see used; counting them would move MAX with every
new endpoint instead of with dead code. Everything else vulture reports at its
default confidence is counted: functions, methods, classes, attributes,
properties, imports, unreachable code.

A false positive goes into vulture_whitelist.py (the file vulture's own
--make-whitelist writes), never into a filter here. Same exact-equality
semantics as scripts/ruff_ratchet.py: MAX moves with the real count in either
direction. vulture is pinned in requirements-dev.txt so the count moves with
the code, not the tool.

Usage: python scripts/vulture_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

WHITELIST = Path(__file__).with_name("vulture_whitelist.py")


def findings() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "vulture", "src/", str(WHITELIST)],
        capture_output=True,
        text=True,
        check=False,
    )
    # vulture exits 3 when it finds dead code; only a crash has no findings on stdout.
    if result.returncode not in (0, 3):
        sys.exit(f"vulture failed (exit {result.returncode}):\n{result.stderr}")
    return [
        line for line in result.stdout.splitlines()
        if line.strip() and ": unused variable " not in line
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    found = findings()
    count = len(found)
    print(f"vulture findings (excluding unused variables): {count}")

    if count > args.max:
        print("\n".join(found))
        print(f"FAIL: {count} findings exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} findings is below ratchet MAX={args.max} — "
            f"dead code was removed; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} findings matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
