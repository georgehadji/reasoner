"""Per-package coverage floor, read from an existing coverage.xml.

architecture-score-9-remediation-plan.md Phase 0.10: a single global coverage
percentage lets newly-written, well-covered code hide behind a large mass of
old covered code — the global 30% floor (coverage.yml) would not budge even
if domain/ or core/ regressed sharply, exactly the packages Phase 4's domain
model rework is about to touch heavily. This gives them their own floor.

Floors are pinned with headroom below the measured baseline at introduction
(domain: 92.3% measured -> 85% floor; core: 81.9% measured -> 75% floor), not
the aspirational 80% target — the same "ratchet, don't aspire" reasoning as
scripts/ruff_ratchet.py.

Usage: python scripts/package_coverage_gate.py --xml coverage.xml \
    --package domain:85 --package core:75
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def package_coverage(root: ET.Element, package_prefix: str) -> tuple[int, int]:
    hit = total = 0
    for pkg in root.iter("package"):
        name = pkg.attrib.get("name", "")
        if name != package_prefix and not name.startswith(package_prefix + "."):
            continue
        for cls in pkg.iter("class"):
            lines = cls.find("lines")
            if lines is None:
                continue
            for line in lines.findall("line"):
                total += 1
                if int(line.attrib.get("hits", 0)) > 0:
                    hit += 1
    return hit, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default="coverage.xml")
    ap.add_argument(
        "--package",
        action="append",
        required=True,
        metavar="NAME:FLOOR",
        help="e.g. domain:85",
    )
    args = ap.parse_args()

    root = ET.parse(Path(args.xml)).getroot()
    failed = False
    for spec in args.package:
        name, floor_str = spec.split(":")
        floor = float(floor_str)
        hit, total = package_coverage(root, name)
        if total == 0:
            print(f"WARN: no coverage data found for package '{name}'")
            continue
        pct = 100 * hit / total
        status = "PASS" if pct >= floor else "FAIL"
        if status == "FAIL":
            failed = True
        print(f"{status}: {name} coverage {pct:.1f}% (floor {floor:.0f}%, {hit}/{total} lines)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
