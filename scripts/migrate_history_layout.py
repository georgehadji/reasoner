"""Move flat history files into per-owner directories.

docs/plans/audit-remediation-3-2026-10-21.md PER-12. History used to be
``history/<id>.json`` for every user; it is now ``history/<owner_key>/<id>.json``
so listing one user's history reads only that user's files. Run once per
deployment:

    PYTHONPATH=src python scripts/migrate_history_layout.py           # dry run
    PYTHONPATH=src python scripts/migrate_history_layout.py --apply

Until the marker file is written the repository still reads and erases the
flat files, so a deploy that comes first shows no gap. The marker is written
last, and only when every file was moved: an unreadable file cannot be
attributed to an owner, so it stays and keeps the flat reads on. Safe to
re-run. The old per-tag ``*.jsonl`` files hold copies of every user's entries
and are no longer read; this script lists them and leaves them for you to
delete.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from reasoner.api.history import HISTORY_DIR
from reasoner.infrastructure.persistence.history_files import LAYOUT_MARKER, owner_key


def migrate(root: Path, apply: bool) -> dict[str, int]:
    moved = skipped = 0
    for path in sorted(root.glob("*.json")):
        try:
            owner = json.loads(path.read_text(encoding="utf-8")).get("user_id") or None
        except (OSError, ValueError, AttributeError) as exc:
            print(f"skip {path.name}: {exc}")
            skipped += 1
            continue
        target = root / owner_key(owner) / path.name
        print(f"{path.name} -> {target.parent.name}/")
        moved += 1
        if not apply:
            continue
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            path.unlink()  # the owner directory already has this entry; it wins
        else:
            os.replace(path, target)
    if apply and skipped == 0:
        (root / LAYOUT_MARKER).write_text("1", encoding="utf-8")
    return {"moved": moved, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="move the files")
    args = parser.parse_args()
    result = migrate(HISTORY_DIR, args.apply)
    for tag_file in sorted(HISTORY_DIR.glob("*.jsonl")):
        print(f"unused tag file (copies of every user's entries): {tag_file.name}")
    print(result)
    if not args.apply:
        print("dry run: pass --apply to write")
