"""processed_webhooks: a lease (status, claimed_at) instead of a permanent claim

Revision ID: 20261021_000200
Revises: 20261021_000150
Create Date: 2026-10-21 00:02:00.000000

The webhook claim was written before processing and never expired, so a worker
that died mid-event left a claim that made the provider's retry look like a
duplicate (docs/plans/audit-remediation-3-2026-10-21.md BIL-21). A claim now
carries a status and a time; a 'processing' claim past the lease may be taken
over. Expand-only: rows that exist today default to 'done', so nothing replays.

The table was created only by the webhook receiver at first use, never by a
migration, so this creates it when absent (the DDL matches the receiver's).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_000200"
down_revision: str | None = "20261021_000150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS processed_webhooks (
            event_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (event_id, provider)
        );
    """)
    op.execute("""
        ALTER TABLE processed_webhooks
            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'done',
            ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE processed_webhooks
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS claimed_at;
    """)
