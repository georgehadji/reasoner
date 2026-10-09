"""Add account_deletion_log (GDPR accountability)

Revision ID: 20260929_000000
Revises: 20260502_001500
Create Date: 2026-09-29 00:00:00.000000

Mirrors migrations/005_account_deletion_log.sql, which nothing executes:
the raw .sql files are not wired into Alembic, so a database provisioned
with `alembic upgrade head` never got this table and GDPR account deletion
(api/saas_router.py inserts into it) failed on it.

The table has NO foreign key to users(id) -- it survives user deletion and
is the audit trail for GDPR Article 17.

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260929_000000"
down_revision: str | None = "20260502_001500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_deletion_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address TEXT,
            user_agent TEXT
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_deletion_log_user
        ON account_deletion_log (user_id);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_deletion_log_deleted_at
        ON account_deletion_log (deleted_at DESC);
    """)


def downgrade() -> None:
    # Deliberately a no-op. This table is the GDPR Article 17 audit trail, so
    # a downgrade must never destroy it. It may also predate this revision
    # (created by hand from migrations/005_account_deletion_log.sql), in which
    # case this revision does not own it. Dropping it is a manual decision.
    pass
