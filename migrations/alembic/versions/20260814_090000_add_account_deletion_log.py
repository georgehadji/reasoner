"""Add account_deletion_log table (GDPR Article 17 accountability)

Revision ID: 20260814_090000
Revises: 20260502_001500
Create Date: 2026-08-14 09:00:00.000000

api/saas_router.py INSERTs into account_deletion_log inside the account-deletion
transaction, but the table was only ever defined in migrations/005_account_deletion_log.sql
— a raw SQL file that nothing executes (docker-entrypoint.sh runs `alembic upgrade
head`, not the numbered .sql files). Account deletion therefore failed outright in
any Alembic-provisioned database. This ports that DDL into the migration chain.

No foreign key to users(id): the row must survive deletion of the user it records.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260814_090000"
down_revision: Union[str, None] = "20260502_001500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.execute("DROP INDEX IF EXISTS idx_account_deletion_log_deleted_at;")
    op.execute("DROP INDEX IF EXISTS idx_account_deletion_log_user;")
    op.execute("DROP TABLE IF EXISTS account_deletion_log;")
