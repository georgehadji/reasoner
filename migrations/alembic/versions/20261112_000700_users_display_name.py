"""Add users.display_name, which provisioning has always written

Revision ID: 20261112_000700
Revises: 20261111_000600
Create Date: 2026-11-12 00:07:00.000000

`api/dependencies._ensure_user_in_db` upserts `display_name`, but no migration
created it (the OAuth columns migration 20260502_001500 added only
`auth_provider` and `avatar_url`). On a database built by `alembic upgrade
head`, every provisioning upsert failed with "column display_name does not
exist"; the error is logged and swallowed, so the user got no `users` row and
credits and API key creation failed later. Found by
tests/integration/test_email_verified_pg.py.

`IF NOT EXISTS`: a database where the column was added by hand is unchanged.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261112_000700"
down_revision: str | None = "20261111_000600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS display_name;")
