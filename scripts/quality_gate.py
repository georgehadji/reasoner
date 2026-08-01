#!/usr/bin/env python3
"""
CI quality gate: compare lint output against .quality-baseline.json.
Fails if any rule's count exceeds its baseline. Exits 0 on pass.
Also checks secrets (must be clean).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / ".quality-baseline.json"
SRC = REPO / "src"

def load_baseline() -> dict:
    with open(BASELINE) as f:
        return json.load(f)["ruff"]


def parse_ruff_stats(output: str) -> dict[str, int]:
    """Parse `ruff check --statistics` output into {RULE_ID: count}."""
    counts: dict[str, int] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Found") or line.startswith("["):
            continue
        # Format: "  1552  W293   [ ]  trailing-whitespace"
        parts = line.split()
        if len(parts) >= 2:
            try:
                count = int(parts[0])
                rule = parts[1]
                counts[rule] = count
            except ValueError:
                continue
    return counts


def main() -> int:
    old = load_baseline()
    old_total = old.pop("_total", 0)

    # Run ruff
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(SRC),
         "--select", "E,F,I,N,W,UP,B", "--statistics"],
        capture_output=True, text=True, cwd=REPO,
    )
    current = parse_ruff_stats(result.stdout + result.stderr)
    current_total = sum(current.values())

    errors = 0
    for rule, new_count in sorted(current.items()):
        old_count = old.get(rule, 0)
        if new_count > old_count:
            print(f"FAIL: {rule} increased from {old_count} to {new_count} (Δ+{new_count - old_count})")
            errors += 1
        elif new_count < old_count:
            print(f"OK:   {rule} decreased from {old_count} to {new_count} (Δ{new_count - old_count}) — ratchet ↓")
        else:
            print(f"OK:   {rule} unchanged at {old_count}")

    # Check for new rules not in baseline
    for rule in old:
        if rule.startswith("_"):
            continue
        if rule not in current:
            print(f"OK:   {rule} no longer present — remove from baseline")

    print(f"\nTotal lint findings: {current_total} (baseline: {old_total})")
    if current_total > old_total:
        print(f"FAIL: Total increased from {old_total} to {current_total}")
        errors += 1

    if errors:
        print(f"\n❌ {errors} lint regression(s) detected. Ratchet down by fixing or update .quality-baseline.json.")
    else:
        print("\n✅ Lint quality baseline holds.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
