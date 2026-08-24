"""Add auth_provider and avatar_url to users table

Revision ID: 20260502_001500
Revises: 20260501_003029
Create Date: 2026-05-02 00:15:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260502_001500"
down_revision: str | None = "20260501_003029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add auth provider tracking (google, github, apple, email)
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS auth_provider TEXT;
    """)

    # Add avatar URL for OAuth profiles
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS avatar_url TEXT;
    """)

    # Create index for provider-based analytics
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_auth_provider
        ON users(auth_provider);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_users_auth_provider;
    """)

    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS avatar_url;
    """)

    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS auth_provider;
    """)
