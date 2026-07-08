-- Migration 004: Add failed_webhook_events table for billing dead-letter storage
--
-- This table is NOT referenced by any FK from `users` — it survives user
-- deletion and provides GDPR accountability (deletion audit trail).
--
-- Phase 0.1 of the REAPER V7 remediation plan.

CREATE TABLE IF NOT EXISTS failed_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    error TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replayed_at TIMESTAMPTZ
);

-- Index for efficient listing by provider (most recent first)
CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_provider
    ON failed_webhook_events (provider, created_at DESC);

-- Partial index for unreplayed events (used by alerting and replay service)
CREATE INDEX IF NOT EXISTS idx_failed_webhook_events_unreplayed
    ON failed_webhook_events (created_at DESC)
    WHERE replayed_at IS NULL;
