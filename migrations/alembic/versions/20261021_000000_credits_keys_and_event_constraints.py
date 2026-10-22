"""Credits, API keys, webhook dead letters and event-store constraints

Revision ID: 20261021_000000
Revises: 20260929_000000
Create Date: 2026-10-21 00:00:00.000000

Alembic is the schema authority (docs/plans/audit-remediation-2-2026-10-20.md
PER-7, Q1). These tables existed only in the raw migrations/004, 007 and 008
.sql files, which nothing executes, so an `alembic upgrade head` database had
no credit ledger, no Postgres api_keys table and no dead-letter table.

Expand-only and idempotent (IF NOT EXISTS throughout): safe on a database
built from those .sql files, on one whose event tables postgres_store.py
created at boot, and on an empty one.

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_000000"
down_revision: str | None = "20260929_000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 004: billing webhook dead letters ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS failed_webhook_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL,
            error TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            replayed_at TIMESTAMPTZ
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_provider "
        "ON failed_webhook_events (provider, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_unreplayed "
        "ON failed_webhook_events (created_at DESC) WHERE replayed_at IS NULL;"
    )

    # ── 007: prepaid credits ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_credits (
            user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            balance           BIGINT NOT NULL DEFAULT 0,
            lifetime_granted  BIGINT NOT NULL DEFAULT 0,
            lifetime_spent    BIGINT NOT NULL DEFAULT 0,
            updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            delta          BIGINT NOT NULL,
            balance_after  BIGINT NOT NULL,
            reason         TEXT NOT NULL,
            reference_id   TEXT,
            description    TEXT,
            created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT credit_ledger_delta_nonzero CHECK (delta <> 0)
        );
    """)
    # The ledger's idempotency guarantee: a replayed reference moves no credits.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_user_reference "
        "ON credit_ledger(user_id, reference_id) WHERE reference_id IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created "
        "ON credit_ledger(user_id, created_at DESC);"
    )

    # ── 007: user-owned API keys ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name          TEXT NOT NULL,
            key_hash      TEXT NOT NULL UNIQUE,
            key_prefix    TEXT NOT NULL,
            scopes        TEXT[] NOT NULL DEFAULT '{}',
            last_used_at  TIMESTAMP WITH TIME ZONE,
            expires_at    TIMESTAMP WITH TIME ZONE,
            revoked_at    TIMESTAMP WITH TIME ZONE,
            created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_hash_live "
        "ON api_keys(key_hash) WHERE revoked_at IS NULL;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id, created_at DESC);")

    # ── Event store: the constraints postgres_store.py's upserts rely on ──
    op.execute("CREATE TABLE IF NOT EXISTS events_default PARTITION OF events DEFAULT;")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_event_id_type "
        "ON events(event_id, aggregate_type);"
    )
    # Snapshots are a cache rebuilt from events, so duplicates are dropped
    # (newest version kept) before the unique index can be created.
    op.execute("""
        DELETE FROM snapshots s USING snapshots t
        WHERE s.aggregate_id = t.aggregate_id
          AND (s.version, s.ctid) < (t.version, t.ctid);
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_aggregate_id "
        "ON snapshots(aggregate_id);"
    )

    # ── 008: payload is ciphertext since E2EE; this GIN index served no query ──
    op.execute("DROP INDEX IF EXISTS idx_events_type;")


def downgrade() -> None:
    # Expand-only: every table here may predate this revision (raw .sql or
    # postgres_store.py), so dropping them could destroy data this revision
    # did not create. Only the snapshot index, which nothing else creates, goes.
    op.execute("DROP INDEX IF EXISTS uq_snapshots_aggregate_id;")
