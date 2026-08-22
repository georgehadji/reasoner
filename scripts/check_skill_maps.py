#!/usr/bin/env python3
"""Detect drift between .claude/skills/map-*/SKILL.md and the folders they map.

Each map skill declares its coverage in frontmatter:

    folders:
      - src/reasoner/api
      - src/reasoner/*          # only files directly in that folder

The file set each map was written against is stored in
.claude/skills/.map-manifest.json. Any add, removal, or rename since then
means that map is stale and needs a pass. A folder listed in no map, or a map
missing from CLAUDE.md, is also reported.

    python scripts/check_skill_maps.py            # report drift, exit 1 if any
    python scripts/check_skill_maps.py --update   # accept current tree as baseline
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
MANIFEST = SKILLS / ".map-manifest.json"
CLAUDE_MD = ROOT / "CLAUDE.md"

_FOLDERS_BLOCK = re.compile(r"^folders:\s*$((?:\n\s*-\s*\S+)+)", re.MULTILINE)


def declared_folders(skill_md: Path) -> list[str]:
    """Read the `folders:` list out of a SKILL.md frontmatter block."""
    head = skill_md.read_text(encoding="utf-8").split("---", 2)
    if len(head) < 3:
        return []
    match = _FOLDERS_BLOCK.search(head[1])
    if not match:
        return []
    return [line.strip().lstrip("-").strip() for line in match.group(1).strip().splitlines()]


def tracked_files() -> list[str]:
    """Tracked files plus untracked ones git would not ignore."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.splitlines()


def files_under(pattern: str, all_files: list[str]) -> list[str]:
    """Files covered by one folder pattern. A trailing /* means non-recursive."""
    if pattern.endswith("/*"):
        base = pattern[:-2].rstrip("/")
        prefix = f"{base}/" if base else ""
        return sorted(
            f for f in all_files if f.startswith(prefix) and "/" not in f[len(prefix) :]
        )
    base = pattern.rstrip("/")
    return sorted(f for f in all_files if f.startswith(f"{base}/"))


def snapshot() -> dict[str, dict[str, list[str]]]:
    all_files = tracked_files()
    snap: dict[str, dict[str, list[str]]] = {}
    for skill_md in sorted(SKILLS.glob("map-*/SKILL.md")):
        folders = declared_folders(skill_md)
        if not folders:
            continue
        snap[skill_md.parent.name] = {p: files_under(p, all_files) for p in folders}
    return snap


def main() -> int:
    update = "--update" in sys.argv
    current = snapshot()

    if not current:
        print("[map] no map-* skill declares a `folders:` block — nothing to check")
        return 0

    if update or not MANIFEST.exists():
        MANIFEST.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        total = sum(len(v) for folders in current.values() for v in folders.values())
        print(f"[map] baseline written: {len(current)} maps, {total} files")
        return 0

    previous = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stale: list[str] = []

    for skill, folders in current.items():
        was = previous.get(skill, {})
        added, removed = [], []
        for pattern, files in folders.items():
            before = set(was.get(pattern, []))
            added += sorted(set(files) - before)
            removed += sorted(before - set(files))
        if added or removed:
            stale.append(skill)
            print(f"\n[map] {skill} is stale ({SKILLS.relative_to(ROOT)}/{skill}/SKILL.md):")
            for f in added:
                print(f"    + {f}   (not described in the map)")
            for f in removed:
                print(f"    - {f}   (gone, but still listed)")

    claude_text = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.exists() else ""
    unmapped = [s for s in current if s not in claude_text]
    if unmapped:
        stale += unmapped
        print(f"\n[map] missing from CLAUDE.md: {', '.join(sorted(unmapped))}")

    if not stale:
        print("[map] skill maps match the tree")
        return 0

    print(
        f"\n[map] {len(set(stale))} map(s) out of date. Update the SKILL.md files "
        "(and CLAUDE.md if a folder was added), then run:\n"
        "    python scripts/check_skill_maps.py --update"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
