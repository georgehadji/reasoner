"""subscriptions: one row per Stripe or PayPal subscription id

Revision ID: 20261110_000400
Revises: 20261029_000300
Create Date: 2026-11-10 00:04:00.000000

`upsert_subscription` selects a row by provider id and inserts when none is
found. Nothing stopped two webhooks arriving together from both inserting, so one
subscription could own two rows that later disagree on tier (audit 6, finding 5).

Decision D3: this migration never deletes billing rows. If duplicates exist it
stops and names them; `scripts/check_duplicate_subscriptions.py` lists them and a
person resolves them. Run that script before deploying.

Expand-only. The indexes are partial (NULL ids are many), and built CONCURRENTLY so
writes are not blocked.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261110_000400"
down_revision: str | None = "20261029_000300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("stripe_sub_id", "paypal_sub_id")


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"""
            DO $$
            DECLARE dupes text;
            BEGIN
                SELECT string_agg({column}, ', ') INTO dupes FROM (
                    SELECT {column} FROM subscriptions
                    WHERE {column} IS NOT NULL
                    GROUP BY {column} HAVING count(*) > 1
                    LIMIT 20
                ) d;
                IF dupes IS NOT NULL THEN
                    RAISE EXCEPTION
                        'duplicate subscriptions.{column} values (first 20): %. '
                        'Run scripts/check_duplicate_subscriptions.py and resolve them first.',
                        dupes;
                END IF;
            END $$;
        """)
    with op.get_context().autocommit_block():
        for column in _COLUMNS:
            op.execute(
                f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_subscriptions_{column} "
                f"ON subscriptions({column}) WHERE {column} IS NOT NULL;"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for column in _COLUMNS:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS uq_subscriptions_{column};")
