"""Partial index for the orphaned-reservation sweep

Revision ID: 20261114_000800
Revises: 20261112_000700
Create Date: 2026-11-14 00:08:00.000000

`list_orphaned_reservations` filters `reference_id LIKE '%:reserve'`, which no
existing index serves, so every sweep scanned the whole ledger. The partial
index holds only reserve rows, ordered by time.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261114_000800"
down_revision: str | None = "20261112_000700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_credit_ledger_reserve_created "
        "ON credit_ledger (created_at) WHERE reference_id LIKE '%:reserve';"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_credit_ledger_reserve_created;")
