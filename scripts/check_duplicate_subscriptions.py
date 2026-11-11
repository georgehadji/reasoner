"""List subscription rows that share a Stripe or PayPal subscription id.

Run before migration 20261110_000400, which refuses to build its unique indexes
while duplicates exist (audit 6, finding 5, decision D3). Read-only: it deletes
nothing. A person decides which row of each group to keep.

    python scripts/check_duplicate_subscriptions.py
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

from reasoner.core.settings import settings

_COLUMNS = ("stripe_sub_id", "paypal_sub_id")


async def find_duplicates(dsn: str) -> dict[str, list[asyncpg.Record]]:
    conn = await asyncpg.connect(dsn)
    try:
        found: dict[str, list[asyncpg.Record]] = {}
        for column in _COLUMNS:
            found[column] = await conn.fetch(
                f"SELECT {column} AS provider_id, count(*) AS rows, "
                f"array_agg(id::text ORDER BY created_at) AS row_ids, "
                f"array_agg(DISTINCT tier) AS tiers "
                f"FROM subscriptions WHERE {column} IS NOT NULL "
                f"GROUP BY {column} HAVING count(*) > 1 ORDER BY count(*) DESC"
            )
        return found
    finally:
        await conn.close()


def main() -> int:
    found = asyncio.run(find_duplicates(settings.DATABASE_URL.replace("+asyncpg", "")))
    total = 0
    for column, rows in found.items():
        for row in rows:
            total += 1
            print(
                f"{column}={row['provider_id']} rows={row['rows']} "
                f"tiers={row['tiers']} ids={row['row_ids']}"
            )
    print(f"{total} duplicated provider id(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
