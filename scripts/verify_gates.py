"""Fail if any expected CI gate marker is missing.

docs/plans/root-cause-remediation-2026-09-07.md (P1) step 2. Pairs with
scripts/gate.py: gate.py writes `.gates/<name>.json` whenever a wrapped
command runs. This script is a workflow's last step, run with `if: always()`
and never with `continue-on-error`, and fails the job if any name in
--expect has no marker file. A step that was skipped, that crashed before
gate.py could wrap it, or a job that died before reaching it, leaves no
marker and turns the job red here — the case D1/D2/D3 each hid instead.

Usage: python scripts/verify_gates.py --expect endpoints,catalogue,alias-honesty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent.parent / ".gates"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", required=True, help="comma-separated gate names")
    args = ap.parse_args()

    expected = [n.strip() for n in args.expect.split(",") if n.strip()]
    missing: list[str] = []

    for name in expected:
        marker = GATES_DIR / f"{name}.json"
        if not marker.exists():
            missing.append(name)
            print(f"MISSING: {name} (no {marker})")
            continue
        data = json.loads(marker.read_text(encoding="utf-8"))
        print(
            f"OK: {name} - ran={data.get('ran')}, "
            f"exit={data.get('final_exit', data.get('command_exit'))}"
        )

    if missing:
        print(f"\nFAIL: {len(missing)} gate(s) never ran: {', '.join(missing)}")
        return 1
    print(f"\nPASS: all {len(expected)} expected gates ran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
