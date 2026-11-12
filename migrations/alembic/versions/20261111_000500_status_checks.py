"""CHECK constraints on subscriptions.status and processed_webhooks.status

Revision ID: 20261111_000500
Revises: 20261110_000400
Create Date: 2026-11-11 00:05:00.000000

docs/plans/implicit-state-machines-2026-11-11.md Phase 3, rows M1 and M2: both
columns were free TEXT, so a typo or an unmodelled status was stored silently.

Both constraints are added NOT VALID: Postgres enforces them for every new or
updated row at once, and does not scan existing rows, so this cannot fail on
data already stored and takes only a brief lock. VALIDATE CONSTRAINT is left to
a later migration, after a production audit:

    SELECT DISTINCT status FROM subscriptions;
    SELECT DISTINCT status FROM processed_webhooks;

Audit on the test database (reasoner_test on :55499, 2026-11-11): neither table
exists there outside the per-test throwaway databases, so no stored value was
seen. The subscriptions list therefore includes the legacy spelling 'canceled'
that migrations/001_saas_init.sql documents (the enum is 'cancelled'), so an old
row can still be updated. Drop 'canceled' from the list once the production
audit shows none.

subscriptions.status: SubscriptionStatus values (domain/saas.py).
processed_webhooks.status: 'processing' and 'done' (migration 20261021_000200).

infrastructure/billing/webhooks.py also creates processed_webhooks on a database
that booted before migrations ran; that table gets the CHECK when this migration
runs, not from that DDL.

Rollback: downgrade drops both constraints, losing no data.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261111_000500"
down_revision: str | None = "20261110_000400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUBSCRIPTION_STATUSES = (
    "active", "trialing", "past_due", "cancelled",
    "incomplete", "unpaid", "paused",
    "canceled",  # legacy spelling from migrations/001_saas_init.sql
)
_WEBHOOK_STATUSES = ("processing", "done")


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscriptions ADD CONSTRAINT ck_subscriptions_status "
        f"CHECK (status IN ({_in_list(_SUBSCRIPTION_STATUSES)})) NOT VALID"
    )
    op.execute(
        "ALTER TABLE processed_webhooks ADD CONSTRAINT ck_processed_webhooks_status "
        f"CHECK (status IN ({_in_list(_WEBHOOK_STATUSES)})) NOT VALID"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE processed_webhooks DROP CONSTRAINT IF EXISTS ck_processed_webhooks_status"
    )
    op.execute("ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS ck_subscriptions_status")
