"""Merge the two audit-2 heads

Revision ID: 20261021_000150
Revises: 20261021_000001, 20261021_000100
Create Date: 2026-10-22 00:01:50.000000

Audit-2 PR 3 (billing, `last_event_at`) and PR 8 (storage, `upload_usage`) were
developed in parallel and both revise `20261021_000000`, so once both are on
`main` Alembic has two heads and `alembic upgrade head` refuses to run. This
revision joins them. It changes no schema.

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20261021_000150"
down_revision: str | Sequence[str] | None = ("20261021_000001", "20261021_000100")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
