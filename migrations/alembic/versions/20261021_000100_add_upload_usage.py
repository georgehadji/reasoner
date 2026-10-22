"""Add upload_usage (per-user upload storage, reserved atomically)

Revision ID: 20261021_000100
Revises: 20261021_000000
Create Date: 2026-10-21 00:01:00.000000

docs/plans/audit-remediation-2-2026-10-20.md PER-8. The upload quota was
summed from a JSON index in the package directory, so it reset on every
deploy and two parallel uploads could both pass it. Usage now lives here and
upload_usage_repo.py reserves with one conditional upsert on user_id.

user_id is TEXT with no foreign key: uploads are keyed by str(user.id), and
account deletion removes the row explicitly.

Run scripts/backfill_upload_usage.py once after this revision, before
relying on the quota: existing users start at zero.

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_000100"
down_revision: str | None = "20261021_000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS upload_usage (
            user_id TEXT PRIMARY KEY,
            bytes BIGINT NOT NULL DEFAULT 0 CHECK (bytes >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS upload_usage;")
