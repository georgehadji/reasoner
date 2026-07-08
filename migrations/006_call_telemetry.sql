-- Migration 006: LLM call telemetry for ACR (Adaptive Capability Router)
--
-- Stores per-call LLM telemetry for adaptive routing analytics.
-- Each row records a single LLM call with identity, performance,
-- quality signals, and circuit-breaker state.
--
-- Part of ACR Phase 1 (Call-Level Telemetry Foundation).
-- See: docs/plans/acr-implementation-plan.md

CREATE TABLE IF NOT EXISTS llm_call_telemetry (
    call_id         TEXT PRIMARY KEY,            -- UUID
    run_id          TEXT NOT NULL,               -- Pipeline run ID
    timestamp       TEXT NOT NULL,               -- ISO-8601 UTC

    -- Model & routing identity
    model_id        TEXT NOT NULL,               -- e.g. "claude-sonnet"
    role            TEXT NOT NULL,               -- e.g. "constructive", "scoring"
    preset_id       TEXT NOT NULL,               -- e.g. "multi-perspective-budget"
    method          TEXT NOT NULL,               -- e.g. "multi-perspective"
    phase           INTEGER NOT NULL,            -- 0-5

    -- Performance
    latency_ms      REAL NOT NULL,               -- Wall-clock time in ms
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    cost_usd        REAL NOT NULL,

    -- Quality / outcome
    success         INTEGER NOT NULL,            -- 0 or 1
    json_valid      INTEGER,                     -- NULL if JSON not expected
    is_fallback     INTEGER NOT NULL DEFAULT 0,
    fallback_reason TEXT,                        -- "timeout", "error", "empty"
    circuit_state   TEXT NOT NULL,               -- "closed", "half_open", "open"

    -- Phase-specific quality (filled post-phase)
    critique_score      REAL,                    -- Phase 3 critique score (0-10)
    stress_test_pass    INTEGER,                 -- Phase 4 pass/fail

    -- Bloc metadata
    vendor          TEXT NOT NULL,
    bloc            TEXT NOT NULL                -- "US", "CN", "EU", "OTHER"
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_telemetry_model_role
    ON llm_call_telemetry(model_id, role);

CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp
    ON llm_call_telemetry(timestamp);

CREATE INDEX IF NOT EXISTS idx_telemetry_role
    ON llm_call_telemetry(role);

CREATE INDEX IF NOT EXISTS idx_telemetry_run
    ON llm_call_telemetry(run_id);

-- Combo index for leaderboard queries
CREATE INDEX IF NOT EXISTS idx_telemetry_role_time
    ON llm_call_telemetry(role, timestamp);
