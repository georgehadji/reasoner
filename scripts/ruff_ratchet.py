"""Ratchet for `ruff check src/` violation count.

Turning on the pyproject.toml-configured lint profile (E,F,I,N,W,UP,B) in CI
surfaced 4606 pre-existing violations — CI previously ran only `--select
B,F821` on the command line, which *replaced* the configured profile rather
than adding to it (ruff CLI --select overrides config select), so E/I/N/W/UP
never actually ran. Hard-blocking on day one would fail every PR and get
bypassed, the exact failure this ratchet avoids: same two-way pattern as
scripts/count_importlinter_exceptions.py — MAX must move in lockstep with the
real count, in either direction, so debt paydown is enforced instead of just
permitted.

Usage: python scripts/ruff_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def count_violations() -> int:
    result = subprocess.run(
        ["ruff", "check", "src/", "--exit-zero", "--output-format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return len(json.loads(result.stdout or "[]"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    count = count_violations()
    print(f"ruff violations: {count}")

    if count > args.max:
        print(f"FAIL: {count} violations exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} violations is below ratchet MAX={args.max} — "
            f"debt was paid down; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} violations matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
