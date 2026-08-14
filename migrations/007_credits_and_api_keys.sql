-- Migration 007: Prepaid credits ledger + user-owned API keys
--
-- Credits are the metered currency for pipeline runs (1 credit = $0.001 of
-- model spend, see reasoner.domain.credits). The ledger is append-only and
-- user_credits is a materialised projection kept in the same transaction.
--
-- API keys are user-owned programmatic credentials (rsn_live_*). Only the
-- SHA-256 hash is stored; the plaintext is shown once at creation.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Credits ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_credits (
    user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance           BIGINT NOT NULL DEFAULT 0,
    lifetime_granted  BIGINT NOT NULL DEFAULT 0,
    lifetime_spent    BIGINT NOT NULL DEFAULT 0,
    updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta          BIGINT NOT NULL,            -- positive = granted, negative = spent
    balance_after  BIGINT NOT NULL,
    reason         TEXT NOT NULL,
    reference_id   TEXT,                       -- idempotency key, unique per user
    description    TEXT,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT credit_ledger_delta_nonzero CHECK (delta <> 0)
);

-- Idempotency: replaying the same reference for a user must not double-charge.
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_user_reference
    ON credit_ledger(user_id, reference_id)
    WHERE reference_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created
    ON credit_ledger(user_id, created_at DESC);

-- ── API keys ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,       -- SHA-256 of the plaintext key
    key_prefix    TEXT NOT NULL,              -- display-only, e.g. "rsn_live_a1b2c3d4"
    scopes        TEXT[] NOT NULL DEFAULT '{}',
    last_used_at  TIMESTAMP WITH TIME ZONE,
    expires_at    TIMESTAMP WITH TIME ZONE,
    revoked_at    TIMESTAMP WITH TIME ZONE,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Hot path: authenticate by hash, only live keys matter.
CREATE INDEX IF NOT EXISTS idx_api_keys_hash_live
    ON api_keys(key_hash)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_api_keys_user
    ON api_keys(user_id, created_at DESC);
