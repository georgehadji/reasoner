"""Set each user's upload_usage from the files already on disk.

docs/plans/audit-remediation-2-2026-10-20.md PER-8. Usage used to be summed
from the upload hash index; it is now a counter in upload_usage, which starts
at zero for every existing user. Run this once after the Alembic revision
20261021_000100, before relying on the quota:

    PYTHONPATH=src python scripts/backfill_upload_usage.py           # dry run
    PYTHONPATH=src python scripts/backfill_upload_usage.py --apply

It counts what file_stored_bytes counts (content, text and vector sidecars)
for every upload whose meta.json names a user, and sets that user's usage to
the total. Safe to re-run: it sets, it does not add.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict

from reasoner.infrastructure.persistence.upload_usage_repo import get_upload_usage_repo
from reasoner.infrastructure.uploader import UPLOAD_DIR, file_stored_bytes


def totals() -> dict[str, int]:
    usage: dict[str, int] = defaultdict(int)
    for meta_path in UPLOAD_DIR.glob("*.meta.json"):
        try:
            owner = json.loads(meta_path.read_text(encoding="utf-8")).get("user_id")
        except (OSError, ValueError) as exc:
            print(f"skip {meta_path.name}: {exc}")
            continue
        if owner:
            usage[owner] += file_stored_bytes(meta_path.name.removesuffix(".meta.json"))
    return dict(usage)


async def main(apply: bool) -> None:
    repo = get_upload_usage_repo()
    for user_id, total in sorted(totals().items()):
        current = await repo.get(user_id)
        print(f"{user_id}: {current} -> {total}")
        if apply and total != current:
            await repo.adjust(user_id, total - current)
    if not apply:
        print("dry run: pass --apply to write")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the totals")
    asyncio.run(main(parser.parse_args().apply))
