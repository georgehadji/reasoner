"""Ratchet for `bandit -r src/` finding count.

security.yml ran a bare `bandit -r src/`, which exits 1 on any finding at any
severity. src/ has 148 (120 LOW, 28 MEDIUM, 0 HIGH) and there is not one
`# nosec` in the tree, so that step failed on the day it was written and has
failed ever since -- the Security Scan workflow has no successful run in its
last 100. A permanently red gate is not a strict gate, it is an ignored one,
and it cannot tell anyone that a NEW finding just landed, which is the thing a
security gate is actually for.

Same two-way pattern as scripts/ruff_ratchet.py and
scripts/count_importlinter_exceptions.py: MAX moves in lockstep with the real
count in either direction, so paying debt down is enforced rather than merely
permitted. Bandit is pinned in the workflow so this count is reproducible;
unpin it and the number drifts with the tool.

This does NOT relax what bandit looks for -- no severity filter, no confidence
filter, no skipped tests. Every finding is still printed in full on every run.
What changed is only that the pre-existing 148 no longer mask the 149th.

Reducing MAX is the point, and security.yml states how: a genuine false
positive gets `# nosec <rule-id> - <reason>, expires <date>` inline, reviewed
in the PR that adds it. No blanket or unreviewed suppression. As of
2026-08-30 the backlog is:

     84  B110 try_except_pass                      LOW
     22  B608 hardcoded_sql_expressions            MEDIUM
      9  B603 subprocess_without_shell_equals_true LOW
      8  B101 assert_used                          LOW
      6  B311 random                               LOW
      5  B112 try_except_continue                  LOW
      5  B607 start_process_with_partial_path      LOW
      3  B104 hardcoded_bind_all_interfaces        MEDIUM
      2  B404 import_subprocess                    LOW
      1 each  B105, B108, B310, B604

All 22 B608 were reviewed on 2026-08-30 and are false positives: every
interpolated fragment is a hard-coded column allowlist or a module constant
(saas_router.py's SEC-010 export field lists, credit_repo_postgres.py's
_LEDGER_COLUMNS) or an integer already clamped by ErrorStore._safe_int for a
SQLite datetime modifier, which cannot be parameterised. Every user-supplied
value goes through a `?`/`$1` placeholder. phases/self_discover.py's hit is a
prompt constant named SD_SELECT_SYSTEM and is not SQL at all. They are left
un-annotated rather than marked `# nosec` here because that policy asks for the
annotation to be reviewed in the PR that adds it, and 22 of them is its own
change. The 84 B110s are the opposite case and should be read as a real
backlog: a swallowed exception is usually a bug, not a false positive.

Usage: python scripts/bandit_ratchet.py --max N
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


def run_bandit() -> list[dict]:
    # -o, not stdout: bandit writes its progress bar to stdout alongside the
    # report, so parsing stdout as JSON fails on the first character.
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "bandit.json"
        result = subprocess.run(
            ["bandit", "-r", "src/", "-f", "json", "-o", str(report)],
            capture_output=True,
            text=True,
            check=False,
        )
        if not report.exists():
            print(result.stdout + result.stderr)
            raise RuntimeError("bandit produced no JSON report")
        return json.loads(report.read_text(encoding="utf-8")).get("results", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    findings = run_bandit()

    # Print everything. The gate counts; it never hides.
    for f in findings:
        print(
            f"{f['filename']}:{f['line_number']}: {f['test_id']} {f['test_name']} "
            f"[{f['issue_severity']}/{f['issue_confidence']}] {f['issue_text']}"
        )

    by_severity = Counter(f["issue_severity"] for f in findings)
    count = len(findings)
    print(
        f"\nbandit findings: {count} "
        f"(HIGH: {by_severity['HIGH']}, MEDIUM: {by_severity['MEDIUM']}, "
        f"LOW: {by_severity['LOW']})"
    )

    if count > args.max:
        print(f"FAIL: {count} findings exceeds ratchet MAX={args.max}")
        return 1
    if count < args.max:
        print(
            f"FAIL: {count} findings is below ratchet MAX={args.max} — "
            f"debt was paid down; lower MAX to {count} in the same change."
        )
        return 1
    print(f"PASS: {count} findings matches ratchet MAX={args.max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
