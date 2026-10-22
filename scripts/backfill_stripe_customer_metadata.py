"""Tag existing Stripe customers with reasoner_user_id (one-off, BIL-13).

Nothing wrote this metadata before docs/plans/audit-remediation-2-2026-10-20.md
PR 3, so webhooks for subscriptions created earlier resolve their user only
through our subscriptions table. This writes it onto each customer that a
subscriptions row names.

Dry run by default: it prints what it would change. Run it for real only after
reading that output:

    python scripts/backfill_stripe_customer_metadata.py           # dry run
    python scripts/backfill_stripe_customer_metadata.py --apply   # writes to Stripe

with DATABASE_URL and STRIPE_SECRET_KEY set.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def main(apply: bool) -> int:
    import asyncpg
    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    conn = await asyncpg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT ON (stripe_customer_id) stripe_customer_id, user_id "
            "FROM subscriptions WHERE stripe_customer_id IS NOT NULL "
            "ORDER BY stripe_customer_id, created_at DESC"
        )
    finally:
        await conn.close()

    changed = 0
    for row in rows:
        customer_id, user_id = row["stripe_customer_id"], str(row["user_id"])
        customer = stripe.Customer.retrieve(customer_id).to_dict()
        current = (customer.get("metadata") or {}).get("reasoner_user_id")
        if current == user_id:
            continue
        if current:
            # Never overwrite a different owner silently: that needs a person.
            print(f"CONFLICT {customer_id}: metadata says {current}, our table says {user_id}")
            continue
        print(f"{'SET' if apply else 'WOULD SET'} {customer_id} reasoner_user_id={user_id}")
        if apply:
            stripe.Customer.modify(customer_id, metadata={"reasoner_user_id": user_id})
        changed += 1
    print(f"{len(rows)} customers checked, {changed} {'updated' if apply else 'to update'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write to Stripe (default: dry run)")
    sys.exit(asyncio.run(main(parser.parse_args().apply)))
