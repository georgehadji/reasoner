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
