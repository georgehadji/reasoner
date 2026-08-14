#!/usr/bin/env python3
"""Generate NOTICE.md — third-party license attribution.

Reasoner ships ~70 Python packages and ~30 npm packages inside its containers
and had no NOTICE, attribution file, or SBOM. Most of those licenses (MIT, BSD,
Apache-2.0) require their notice text to be reproduced in distributions, so
shipping without one is a licence-compliance gap regardless of how permissive
the licences are.

    python scripts/generate_notice.py            # write NOTICE.md
    python scripts/generate_notice.py --check    # fail if NOTICE.md is stale

Run this after changing requirements.txt or ui-next/package.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTICE = REPO_ROOT / "NOTICE.md"

HEADER = """# Third-Party Notices

Reasoner bundles the third-party software listed below. Each remains under its
own licence and copyright; this file reproduces the attribution those licences
require. Nothing here grants rights to Reasoner itself, which is MIT-licensed —
see [LICENSE](LICENSE).

Regenerate with `python scripts/generate_notice.py` after changing
`requirements.txt` or `ui-next/package.json`.

"""

# Licences that need more than attribution — flagged rather than silently listed,
# because a copyleft dependency in a distributed container is a real decision.
COPYLEFT_MARKERS = ("GPL", "AGPL", "LGPL", "MPL", "EPL", "CDDL")


def shipped_distributions() -> set[str]:
    """Names pinned in requirements.lock — i.e. what the image actually installs.

    Without this filter the notice inventories whatever happens to be in the
    developer's virtualenv, which includes local tooling that is never shipped
    and, worse, can list a package (pymupdf) that was deliberately excluded from
    the distribution for licence reasons.
    """
    lock = REPO_ROOT / "requirements.lock"
    if not lock.exists():
        return set()
    names = set()
    for line in lock.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("==")[0].split("[")[0].strip()
        if name:
            names.add(name.lower().replace("_", "-"))
    return names


def python_packages() -> list[dict[str, str]]:
    """Inventory the Python distributions this project ships, with licences."""
    out = subprocess.run(
        [
            sys.executable, "-m", "piplicenses",
            "--format=json", "--with-urls", "--with-authors",
        ],
        capture_output=True, text=True, check=True,
    )
    packages = json.loads(out.stdout)
    shipped = shipped_distributions()
    return sorted(
        (
            p for p in packages
            if not shipped or p["Name"].lower().replace("_", "-") in shipped
        ),
        key=lambda p: p["Name"].lower(),
    )


def npm_packages() -> list[dict[str, str]]:
    """Inventory production npm dependencies declared in package.json."""
    pkg_json = REPO_ROOT / "ui-next" / "package.json"
    if not pkg_json.exists():
        return []
    data = json.loads(pkg_json.read_text(encoding="utf-8"))
    deps = data.get("dependencies", {})
    rows = []
    for name, version in sorted(deps.items()):
        licence = "See package"
        # Read the licence from the installed package when node_modules is present.
        meta = REPO_ROOT / "ui-next" / "node_modules" / name / "package.json"
        if meta.exists():
            try:
                info = json.loads(meta.read_text(encoding="utf-8"))
                raw = info.get("license") or info.get("licenses")
                if isinstance(raw, list) and raw:
                    raw = raw[0].get("type") if isinstance(raw[0], dict) else raw[0]
                if isinstance(raw, dict):
                    raw = raw.get("type")
                licence = raw or licence
            except Exception:
                pass
        rows.append({"Name": name, "Version": str(version), "License": licence})
    return rows


def render() -> str:
    py = python_packages()
    npm = npm_packages()
    lines = [HEADER]

    flagged: list[str] = []

    lines.append(f"## Python ({len(py)} packages)\n")
    lines.append("| Package | Version | License |")
    lines.append("| :--- | :--- | :--- |")
    for p in py:
        licence = p.get("License", "UNKNOWN")
        if any(m in licence.upper() for m in COPYLEFT_MARKERS):
            flagged.append(f"{p['Name']} ({licence})")
        lines.append(f"| {p['Name']} | {p.get('Version', '')} | {licence} |")

    lines.append(f"\n## JavaScript ({len(npm)} runtime packages)\n")
    lines.append("| Package | Version | License |")
    lines.append("| :--- | :--- | :--- |")
    for p in npm:
        licence = p["License"]
        if any(m in licence.upper() for m in COPYLEFT_MARKERS):
            flagged.append(f"{p['Name']} ({licence})")
        lines.append(f"| {p['Name']} | {p['Version']} | {licence} |")

    if flagged:
        lines.append("\n## Licences needing review\n")
        lines.append(
            "These carry obligations beyond attribution. Confirm each is compatible "
            "with how you distribute Reasoner before shipping:\n"
        )
        for item in sorted(set(flagged)):
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if NOTICE.md is missing or stale"
    )
    args = parser.parse_args()

    content = render()

    if args.check:
        if not NOTICE.exists():
            print("NOTICE.md is missing — run: python scripts/generate_notice.py")
            return 1
        # Compare package tables only; counts and ordering are what matter.
        if NOTICE.read_text(encoding="utf-8").strip() != content.strip():
            print("NOTICE.md is stale — run: python scripts/generate_notice.py")
            return 1
        print("NOTICE.md is current")
        return 0

    NOTICE.write_text(content, encoding="utf-8")
    print(f"Wrote {NOTICE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
