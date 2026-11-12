-- Migration 005: Account deletion log (GDPR accountability)
--
-- This table has NO foreign key to users(id) — it survives user deletion
-- and provides GDPR Article 17 accountability (audit trail of deletions).
--
-- Phase 0.2 of the REAPER V7 remediation plan.

CREATE TABLE IF NOT EXISTS account_deletion_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_account_deletion_log_user
    ON account_deletion_log (user_id);

CREATE INDEX IF NOT EXISTS idx_account_deletion_log_deleted_at
    ON account_deletion_log (deleted_at DESC);

-- Erase status and one row per user (Alembic 20261111_000600, SM-M7).
ALTER TABLE account_deletion_log ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'erased';
ALTER TABLE account_deletion_log ALTER COLUMN status SET DEFAULT 'requested';
ALTER TABLE account_deletion_log ADD COLUMN IF NOT EXISTS detail TEXT;
DELETE FROM account_deletion_log a USING account_deletion_log b
    WHERE a.user_id = b.user_id AND (b.deleted_at, b.id) < (a.deleted_at, a.id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_log_user ON account_deletion_log (user_id);
ALTER TABLE account_deletion_log ADD CONSTRAINT ck_account_deletion_log_status
    CHECK (status IN ('requested', 'erasing', 'erased', 'partial')) NOT VALID;
