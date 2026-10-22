"""subscriptions.last_event_at: apply billing webhooks in event order

Revision ID: 20261021_000001
Revises: 20261021_000000
Create Date: 2026-10-21 00:00:01.000000

Webhook retries (BIL-4) and the dead-letter replay re-apply payload
snapshots. Without an ordering guard a retried "updated(active)" landing
after "deleted" reactivated a cancelled plan
(docs/plans/audit-remediation-2-2026-10-20.md BIL-15). A write now applies
only when its event is not older than the last one applied.

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_000001"
down_revision: str | None = "20261021_000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;")
    # The baseline declared both NOT NULL, but the repository never writes
    # current_period_start and a provider event can lack the end. On an
    # Alembic-built database the first webhook for every new subscriber failed
    # on this insert. Found by tests/integration/test_audit2_billing_pg.py.
    op.execute("""
        ALTER TABLE subscriptions
            ALTER COLUMN current_period_start DROP NOT NULL,
            ALTER COLUMN current_period_end DROP NOT NULL;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS last_event_at;")
