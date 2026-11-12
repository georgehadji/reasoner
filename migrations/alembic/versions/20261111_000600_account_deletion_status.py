"""account_deletion_log: erase status, one row per user

Revision ID: 20261111_000600
Revises: 20261111_000500
Create Date: 2026-11-11 00:06:00.000000

A deletion that failed part-way left the account refused (403) with no record of
what was left and no way to finish: the log row said only "deleted" (SM-M7). The
row now carries ``status`` (requested, erasing, erased, partial) and ``detail``
(names of the stores that failed), and ``user_id`` is unique so a repeat DELETE
resumes the one row instead of adding another.

Existing rows are completed deletions under the old flow, so they backfill to
'erased'; new rows default to 'requested'. Duplicate rows per user are removed
first, keeping the earliest (``deleted_at``, then ``id``): that is the accountable
record of when the deletion began. The CHECK is added NOT VALID; validate it
after `SELECT DISTINCT status FROM account_deletion_log`.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261111_000600"
down_revision: str | None = "20261111_000500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "ALTER TABLE account_deletion_log"
    op.execute(f"{table} ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'erased';")
    op.execute(f"{table} ALTER COLUMN status SET DEFAULT 'requested';")
    op.execute(f"{table} ADD COLUMN IF NOT EXISTS detail TEXT;")
    op.execute("""
        DELETE FROM account_deletion_log a USING account_deletion_log b
        WHERE a.user_id = b.user_id AND (b.deleted_at, b.id) < (a.deleted_at, a.id);
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_log_user
        ON account_deletion_log (user_id);
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_account_deletion_log_status'
            ) THEN
                ALTER TABLE account_deletion_log ADD CONSTRAINT ck_account_deletion_log_status
                    CHECK (status IN ('requested', 'erasing', 'erased', 'partial')) NOT VALID;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Duplicate rows removed by upgrade() are not restored.
    table = "ALTER TABLE account_deletion_log"
    op.execute(f"{table} DROP CONSTRAINT IF EXISTS ck_account_deletion_log_status;")
    op.execute("DROP INDEX IF EXISTS uq_account_deletion_log_user;")
    op.execute(f"{table} DROP COLUMN IF EXISTS detail;")
    op.execute(f"{table} DROP COLUMN IF EXISTS status;")
