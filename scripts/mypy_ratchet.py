"""Ratchet for `mypy src/reasoner` violation count.

CI previously ran `mypy --strict` against exactly one file
(infrastructure/auth_legacy.py) — decorative type-checking that never
touched the other ~250 source files. Running the pyproject.toml-configured
(non-strict) profile over the full tree surfaced 429 pre-existing errors
across 128 files. Hard-blocking on day one would fail every PR immediately,
so this ratchets the same two-way way as scripts/ruff_ratchet.py and
scripts/count_importlinter_exceptions.py: MAX must move in lockstep with the
real count, in either direction.

The existing `mypy --strict auth_legacy.py` check is kept alongside this,
unchanged — that file is already clean under --strict and stays that way.

Usage: python scripts/mypy_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

SUMMARY_RE = re.compile(r"Found (\d+) errors? in \d+ files?")


def count_errors() -> int:
    result = subprocess.run(
        ["mypy", "src/reasoner", "--ignore-missing-imports"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    match = SUMMARY_RE.search(output)
    if match:
        return int(match.group(1))
    if "Success: no issues found" in output:
        return 0
    print(output)
    raise RuntimeError("Could not parse mypy summary line")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    count = count_errors()
    print(f"mypy errors: {count}")

    if count > args.max:
        print(f"FAIL: {count} errors exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} errors is below ratchet MAX={args.max} — "
            f"debt was paid down; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} errors matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
