"""Semantic counter for `.importlinter`'s `ignore_imports` exception list.

Replaces `grep -c '\\->'` in CI (pr-architecture.yml) and ci-local.sh, which
counts ASCII "->" anywhere in the file — including inside prose comments —
rather than only real ignore_imports entries. Parses via configparser so a
comment containing "->" can never inflate the count.

Usage: python scripts/count_importlinter_exceptions.py [--max N]
Exits 0 and prints the count if --max is omitted.
With --max N: ratchets both ways — fails if COUNT > N (new debt added
without raising the budget) or COUNT < N (debt was paid down but MAX
wasn't lowered to match, letting the freed budget silently regrow).
"""

from __future__ import annotations

import argparse
import configparser
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / ".importlinter"


def count_exceptions(config_path: Path = CONFIG_PATH) -> int:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    raw = parser.get("importlinter:contract:1", "ignore_imports", fallback="")
    return sum(
        1
        for line in raw.splitlines()
        if (entry := line.strip()) and not entry.startswith("#")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()

    count = count_exceptions()
    print(f"Import-linter exceptions: {count}")

    if args.max is None:
        return 0

    if count > args.max:
        print(f"FAIL: {count} exceptions exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} exceptions is below ratchet MAX={args.max} — "
            f"debt was paid down; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} exceptions matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
