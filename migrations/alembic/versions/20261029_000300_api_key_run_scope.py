"""api_keys: a `run` scope on every existing key, and last_run_at

Revision ID: 20261029_000300
Revises: 20261021_000200
Create Date: 2026-10-29 00:03:00.000000

Starting a billed run now needs the `run` scope (docs/plans/
audit-remediation-5-2026-10-29.md SEC-19). Decision Q1 is grandfather, measure,
then tighten. This revision is step 1: every existing key gets `run`, so no
integration breaks on deploy. `last_run_at` records which keys actually start
runs. Step 2, a later revision 30 days after deploy, removes `run` from keys
that hold neither `write` nor a recorded run.

Expand-only. The downgrade removes the column and the scope it added, so it also
takes `run` from keys minted with it after the upgrade.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261029_000300"
down_revision: str | None = "20261021_000200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;")
    op.execute(
        "UPDATE api_keys SET scopes = array_append(scopes, 'run') "
        "WHERE NOT ('run' = ANY(scopes));"
    )


def downgrade() -> None:
    op.execute("UPDATE api_keys SET scopes = array_remove(scopes, 'run');")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS last_run_at;")
