"""Template-Method wrapper for CI gates: run a command, prove it ran.

docs/plans/root-cause-remediation-2026-09-07.md (P1). A green CI step today
means "exited 0, or continue-on-error told GitHub not to care" — never "the
assertion was evaluated". D1: `--check-endpoints` crashed on
`ModuleNotFoundError` and `continue-on-error` reported success for every
scheduled run since it was added. This wrapper makes "ran" a checkable fact
instead of an inference from the exit code: every invocation writes
`.gates/<name>.json` before it re-raises the command's exit code, so a step
that crashed before producing output still leaves proof it was attempted.
scripts/verify_gates.py then tells "never ran" apart from "ran, exited
nonzero, was allowed to continue via continue-on-error".

Usage:
    python scripts/gate.py --name endpoints -- python scripts/update_openrouter_catalogue.py --check-endpoints
    python scripts/gate.py --name catalogue --expect-stdout "no drift|models added|models removed" -- python scripts/update_openrouter_catalogue.py --check

--expect-stdout distinguishes "ran and found nothing" from "never ran" on an
advisory step (continue-on-error: true in the workflow): if the command exits
0 but its stdout does not match the regex, gate.py exits 1 anyway, so the
marker records a real failure even on a step the workflow is allowed to
shrug off.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent.parent / ".gates"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--expect-stdout", default=None, help="regex the command's stdout must match")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("gate.py: no command given (pass it after ' -- ')", file=sys.stderr)
        return 2

    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True)
    duration = time.time() - started

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    exit_code = result.returncode
    stdout_matched = True
    if args.expect_stdout is not None:
        stdout_matched = bool(re.search(args.expect_stdout, result.stdout))
        if not stdout_matched and exit_code == 0:
            exit_code = 1

    GATES_DIR.mkdir(exist_ok=True)
    marker = {
        "name": args.name,
        "ran": True,
        "command_exit": result.returncode,
        "final_exit": exit_code,
        "expect_stdout": args.expect_stdout,
        "stdout_matched": stdout_matched,
        "duration_s": round(duration, 2),
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }
    (GATES_DIR / f"{args.name}.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
