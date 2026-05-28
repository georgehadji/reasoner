# Reasoner Architecture Risk Mitigation Plan

This document outlines a phased, safe execution plan to address the architectural and operational risks identified in the recent forensic analysis. 

The strategy prioritizes zero-downtime rollouts, strong backward compatibility during data migrations, and establishing testing/observability foundations *before* touching critical path persistence logic.

## Phase 1: Testing & Observability Foundations
*Goal: Establish a safe environment for development and ensure visibility into any failures caused by subsequent phases.*

### 1.1. Automated Test State Isolation (Action 4.1)
- **Target:** `tests/conftest.py` (Create or update)
- **Implementation:** Implement an `autouse=True` pytest fixture that explicitly invokes `reset_event_bus()`, clears the `_langfuse_client` and `_langfuse_subscriber` singletons, and flushes the `get_token_cache()` instance before and after each test.
- **Safety:** Zero risk to production. Prevents flaky tests during the complex refactoring in later phases.

### 1.2. Observability Strictness & Metrics (Actions 3.1, 3.2)
- **Target:** `src/reasoner/infrastructure/observability/langfuse_subscriber.py`, `src/reasoner/api/__init__.py`, `src/reasoner/api/metrics.py`
- **Implementation:** 
  1. Add a Prometheus counter `observability_events_dropped_total`.
  2. Update `_setup_langfuse` to increment this counter when `_is_langfuse_enabled` is False but events are being received.
  3. Add a startup check in `api/__init__.py` that logs a `CRITICAL` warning to Sentry/stdout if `ENVIRONMENT=production` but Langfuse keys are missing.
- **Safety:** Purely additive. Enhances visibility without altering core logic.

## Phase 2: Resilience & Error Handling
*Goal: Prevent cascading failures and handle corrupted data gracefully.*

### 2.1. Graceful Decryption Failures (Actions 2.4, 2.5)
- **Target:** `src/reasoner/infrastructure/persistence/postgres_store.py`
- **Implementation:**
  1. Wrap `json.loads` inside `_deserialize_event`, `get_snapshot`, and `get_read_model` with a specific `except json.JSONDecodeError`.
  2. On failure, log a high-severity alert, emit an `ErrorOccurred` domain event to the `EventBus` (for DLQ logging), and return `None` (or skip the corrupted event in the stream sequence).
- **Safety:** Prevents the entire application or read-model projection from crashing due to a single corrupted row.

### 2.2. PostgreSQL Connection Resilience (Actions 1.1, 1.2)
- **Target:** `src/reasoner/infrastructure/persistence/postgres_store.py` (`save_events`, `save_snapshot`)
- **Implementation:**
  1. Introduce the `tenacity` library for exponential backoff retries on `asyncpg.PostgresError` or `ConnectionError`.
  2. Limit retries (e.g., max 3 attempts) to prevent API thread starvation.
  3. Implement a simple circuit breaker state (e.g., using `aiocircuitbreaker`) to fast-fail subsequent requests if the database is definitively down, shedding load.
- **Safety:** Introduce gradually. Monitor retry counts via metrics before tightening circuit breaker thresholds.

## Phase 3: Event Bus Fortification
*Goal: Ensure critical domain events are not silently dropped under heavy load.*

### 3.1. Differentiated Queue Handling (Actions 2.1, 2.2, 2.3)
- **Target:** `src/reasoner/application/event_bus/bus.py`
- **Implementation:**
  1. Categorize events. Critical events (e.g., `PIPELINE_COMPLETED`, billing/SaaS events) vs. non-critical (e.g., `PHASE_STARTED`).
  2. Modify `EventBus.publish`: For critical events, if the queue is full, bypass `put_nowait` and use `await self._task_queue.put()` (applying backpressure to the caller) or immediately write to the `_DEAD_LETTER_PATH`.
  3. Ensure the Dead-Letter Queue mechanism captures queue-full rejections, not just handler execution failures.
- **Safety:** By applying backpressure only to critical events, we maintain system stability while guaranteeing data consistency for vital state changes.

## Phase 4: Production Safeguards & Data Migration
*Goal: Enforce production constraints and secure legacy data. (High Risk)*

### 4.1. Strict Production Rate Limiting (Action 1.5)
- **Target:** `src/reasoner/rate_limiter.py`, `src/reasoner/api/__init__.py`
- **Implementation:** 
  1. In `RateLimiter.__init__`, if `os.environ.get("ENVIRONMENT") == "production"` and `RATE_LIMITER_MODE != "redis"`, raise a fatal `RuntimeError`.
  2. If the Redis connection fails during initialization in production, fail the application startup rather than silently falling back to the in-memory bucket.
- **Safety:** This is a breaking change for misconfigured production environments. Must be coordinated with DevOps to ensure correct `RATE_LIMITER_MODE` and Redis credentials are injected prior to deployment.

### 4.2. Envelope Encryption Migration Script (Action 1.4)
- **Target:** `scripts/migrate_encryption_v2.py` (New standalone script)
- **Implementation:**
  1. Write an idempotent background script that connects to the database.
  2. Query `events` and `snapshots` where the `payload` does not contain the `{"_e": ...}` wrapper (or lacks `_blind_index`).
  3. Decrypt the legacy Fernet string, extract text fields, generate the blind index via `EncryptionService`, wrap in the new JSON structure, and execute an `UPDATE`.
  4. Process in small batches (e.g., 500 rows) with sleep intervals to avoid impacting production DB performance.
- **Safety:** Run this as an out-of-band operational task during off-peak hours. Because `_deserialize_event` currently supports reading both formats safely, the application can continue running normally while the migration occurs in the background.

---
**Sign-off required prior to Phase 4 execution.**