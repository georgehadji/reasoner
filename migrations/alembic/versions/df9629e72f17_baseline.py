"""Baseline — all PostgreSQL schema

Revision ID: df9629e72f17
Revises:
Create Date: 2026-04-26 00:00:00.000000

This baseline consolidates all PostgreSQL schema from:
- migrations/001_saas_init.sql (with period_start fix)
- migrations/002_auth_audit.sql
- src/reasoner/infrastructure/persistence/postgres_store.py (_init_schema)
- Missing query_log table (used by PostgresQuotaRepository)

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "df9629e72f17"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extensions ──
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # ── SaaS tables (from 001_saas_init.sql, fixed) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP WITH TIME ZONE,
            email_verified BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tier TEXT NOT NULL,
            status TEXT NOT NULL,
            current_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
            current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
            cancel_at_period_end BOOLEAN DEFAULT FALSE,
            external_customer_id TEXT,
            external_subscription_id TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # NOTE: usage_quotas schema aligned with PostgresQuotaRepository expectations
    op.execute("""
        CREATE TABLE IF NOT EXISTS usage_quotas (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tier TEXT NOT NULL,
            used_queries INTEGER DEFAULT 0,
            max_queries INTEGER DEFAULT 0,
            period_start TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS query_audit_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            query_text_hash TEXT NOT NULL,
            response_summary TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd DECIMAL(10, 6),
            model_id TEXT NOT NULL,
            pipeline_id UUID NOT NULL,
            is_success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ── Auth audit log (from 002_auth_audit.sql) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ── Missing query_log table (used by PostgresQuotaRepository) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            preset TEXT,
            method TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd DECIMAL(10, 6),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ── Event store tables (from postgres_store.py) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL,
            event_id UUID UNIQUE NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            aggregate_id VARCHAR(255) NOT NULL,
            aggregate_type VARCHAR(50) NOT NULL DEFAULT 'pipeline',
            version INTEGER NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, aggregate_type)
        ) PARTITION BY LIST (aggregate_type);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS events_pipeline
            PARTITION OF events FOR VALUES IN ('pipeline');
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS events_widget
            PARTITION OF events FOR VALUES IN ('widget');
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS events_memory
            PARTITION OF events FOR VALUES IN ('memory');
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS events_generic
            PARTITION OF events FOR VALUES IN ('generic');
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS aggregates (
            aggregate_id VARCHAR(255) PRIMARY KEY,
            aggregate_type VARCHAR(50) NOT NULL,
            current_version INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            problem TEXT,
            preset VARCHAR(100),
            method VARCHAR(100),
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id BIGSERIAL PRIMARY KEY,
            aggregate_id VARCHAR(255) NOT NULL,
            version INTEGER NOT NULL,
            state JSONB NOT NULL,
            snapshot_type VARCHAR(50) DEFAULT 'full',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS read_models (
            model_name VARCHAR(100) NOT NULL,
            model_key VARCHAR(255) NOT NULL,
            data JSONB NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (model_name, model_key)
        );
    """)

    # ── Indexes ──
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_usage_quotas_user_id ON usage_quotas(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_query_audit_logs_user_id ON query_audit_logs(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_query_audit_logs_timestamp ON query_audit_logs(timestamp);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit_log(user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_audit_event ON auth_audit_log(event_type, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_query_log_user_created ON query_log (user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions (user_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_usage_quotas_period ON usage_quotas (period_start);")

    # Event store indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, version);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events USING GIN (payload);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_search ON events USING GIN (to_tsvector('english', payload::text));")

    # Aggregate update trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_aggregates_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS update_aggregates_updated_at_trigger ON aggregates;
    """)
    op.execute("""
        CREATE TRIGGER update_aggregates_updated_at_trigger
        BEFORE UPDATE ON aggregates
        FOR EACH ROW
        EXECUTE FUNCTION update_aggregates_updated_at();
    """)


def downgrade() -> None:
    # Downgrade is destructive — drops all tables created in baseline.
    # Use with extreme caution in production.
    op.execute("DROP TRIGGER IF EXISTS update_aggregates_updated_at_trigger ON aggregates;")
    op.execute("DROP FUNCTION IF EXISTS update_aggregates_updated_at;")
    op.execute("DROP TABLE IF EXISTS read_models;")
    op.execute("DROP TABLE IF EXISTS snapshots;")
    op.execute("DROP TABLE IF EXISTS aggregates;")
    op.execute("DROP TABLE IF EXISTS events_generic;")
    op.execute("DROP TABLE IF EXISTS events_memory;")
    op.execute("DROP TABLE IF EXISTS events_widget;")
    op.execute("DROP TABLE IF EXISTS events_pipeline;")
    op.execute("DROP TABLE IF EXISTS events;")
    op.execute("DROP TABLE IF EXISTS query_log;")
    op.execute("DROP TABLE IF EXISTS auth_audit_log;")
    op.execute("DROP TABLE IF EXISTS query_audit_logs;")
    op.execute("DROP TABLE IF EXISTS usage_quotas;")
    op.execute("DROP TABLE IF EXISTS subscriptions;")
    op.execute("DROP TABLE IF EXISTS users;")
