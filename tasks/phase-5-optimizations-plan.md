# Phase 5 Optimizations: Master Implementation Plan

This document outlines the detailed implementation strategy for three high-impact optimizations identified during the Phase 5 (Scale Prep) review. These enhancements address broken functionality, scalability limitations, and observability gaps.

## 1. PostgreSQL Encryption Blindspot Fix (Blind Indexing & Envelope Encryption)

**Problem:** The current End-to-End Encryption (E2EE) implementation in `PostgreSQLEventStore` encrypts the entire JSON payload into a `{"_e": "..."}` block. This breaks PostgreSQL's `to_tsvector` full-text search and GIN indexing, as the database is trying to index encrypted gibberish.

**Goal:** Restore searchability and indexing while maintaining data privacy by implementing Envelope Encryption with Blind Indexing.

### Implementation Steps:

1. **Schema Update (`src/reasoner/infrastructure/persistence/postgres_store.py`)**
   - No strict schema change is needed for `events` table since `payload` is `JSONB`, but we need to change how we structure the JSON.
   - We will introduce a new `blind_index` array field inside the `JSONB` payload or as a separate indexed column. For simplicity, we can store it in the JSONB.
   - Update the full-text search index (`idx_events_search`) to target specific plaintext fields or the blind index, rather than the whole payload.

2. **Refactor Encryption Service (`src/reasoner/security/encryption.py`)**
   - Add a `generate_blind_index(text: str) -> list[str]` method. This method will:
     - Normalize the text (lowercase, remove punctuation, stop words).
     - Tokenize the text.
     - Generate a deterministic HMAC-SHA256 hash for each token using a dedicated "blind index secret".

3. **Update Event Serialization (`PostgreSQLEventStore.save_events`)**
   - Instead of encrypting the entire `raw_payload`, separate it into:
     - `public_metadata`: Non-sensitive fields (e.g., `tokens`, `duration`, `model_id`).
     - `sensitive_data`: Fields containing user input/output (e.g., `problem`, `content`, `rationale`).
   - Encrypt only `sensitive_data` into `{"_e": "..."}`.
   - Generate blind index hashes from the `sensitive_data` text values and store them in a `_blind_index` array.
   - The final payload stored in PostgreSQL will look like:
     ```json
     {
       "metadata": {"model": "gpt-4", "tokens": 150},
       "_e": "<encrypted_sensitive_data>",
       "_blind_index": ["hash1", "hash2", "hash3"]
     }
     ```

4. **Update Search Logic (`PostgreSQLEventStore.search_events`)**
   - When a user searches for a term, run the search query through `generate_blind_index()`.
   - Modify the SQL query to search the `_blind_index` array using the generated hashes instead of using `plainto_tsquery` on the encrypted payload.

5. **Migration Strategy**
   - Since old data is fully encrypted without blind indexes, we will need a background script to fetch old events, decrypt them, generate blind indexes, re-format the payload, and update the rows.

## 2. Distributed Rate Limiter with Atomic Redis Lua Scripting

**Problem:** The current `RateLimiter` uses in-memory `defaultdict` and `asyncio.Lock()`. In a multi-worker setup (e.g., Gunicorn with 4 workers), each worker tracks its own limits, allowing clients to bypass limits by hitting different workers.

**Goal:** Migrate the Token Bucket algorithm to Redis using atomic Lua scripting to ensure global consistency without locking overhead.

### Implementation Steps:

1. **Lua Script Development (`src/reasoner/infrastructure/redis/scripts/rate_limit.lua`)**
   - Write a Lua script that implements the Token Bucket algorithm.
   - Inputs: `KEYS[1]` (client_id bucket), `ARGV[1]` (refill_rate), `ARGV[2]` (burst_capacity), `ARGV[3]` (current_time), `ARGV[4]` (requested_tokens).
   - Logic:
     - Get current tokens and last update time.
     - Calculate elapsed time and add refilled tokens (cap at burst_capacity).
     - Check if requested tokens are available.
     - If yes, decrement and save new state.
     - If no, return false and retry_after.
   - Return: `[allowed (1/0), tokens_remaining, retry_after_ms]`.

2. **Refactor RateLimiter (`src/reasoner/rate_limiter.py`)**
   - Import the shared Redis client from `src/reasoner/infrastructure/redis/client.py`.
   - Load the Lua script into Redis via `Script` object caching (`client.register_script`).
   - Replace `is_allowed_for_user` and `is_allowed` logic to invoke the Lua script instead of the in-memory dictionary.
   - Fallback mechanism: If Redis is unavailable, temporarily fall back to the in-memory implementation to maintain availability, but log a critical alert.

3. **Windowed Limits (Per-Minute/Per-Hour)**
   - The Lua script can be extended to use Redis `INCR` with `EXPIRE` for the sliding/fixed windows to handle the `requests_minute` and `requests_hour` limits alongside the token bucket.

## 3. LLM-Native Observability Integration (Event Bus to Langfuse)

**Problem:** Current APM (Sentry) traces basic HTTP requests but provides zero visibility into the multi-step Agentic reasoning loops (e.g., prompt inputs, LLM outputs, token usage per phase, critique scores).

**Goal:** Integrate an LLM-native observability platform (e.g., Langfuse or Arize Phoenix) via the existing Domain Event Bus to automatically build hierarchical traces of pipeline execution.

### Implementation Steps:

1. **Dependency Addition**
   - Add the chosen SDK (e.g., `langfuse-python`) to `pyproject.toml` / `requirements.txt`.

2. **Observability Subscriber (`src/reasoner/infrastructure/observability/langfuse_subscriber.py`)**
   - Create a new module that listens to `EventBus` events.
   - State management: Since traces are hierarchical (Trace -> Span -> Generation), we need to map `pipeline_id` to a Trace, and `phase_name` to a Span. We can use Redis or an in-memory LRU cache to hold active Trace/Span IDs.
   - Event Mappings:
     - `PipelineStarted` -> Create a new Trace.
     - `PhaseStarted` -> Create a new Span under the Trace.
     - `ModelCallCompleted` (Need to emit this from `WorkflowServices.call_llm`) -> Create a Generation under the Span, logging the system prompt, user prompt, raw response, model name, and token usage.
     - `PhaseCompleted` -> End the Span.
     - `PipelineCompleted` / `PipelineFailed` -> End the Trace.

3. **Event Bus Registration (`src/reasoner/application/event_bus/bus.py`)**
   - Import and initialize the new subscriber in `init_default_subscribers()`.
   - Ensure the initialization is guarded by environment variables (e.g., `LANGFUSE_PUBLIC_KEY`) so it degrades gracefully if observability is not configured.

4. **Enhance LLM Call Events (`src/reasoner/application/flows/base.py`)**
   - Update `WorkflowServices.call_llm` to emit a specific domain event (e.g., `LLMGenerationCompleted`) containing the exact prompt templates and raw string outputs, ensuring the observability subscriber has the data it needs to build rich generation logs.

## Execution Order

1. **Redis Rate Limiter**: High priority for production stability and immediate cluster readiness.
2. **PostgreSQL Blind Indexing**: Medium priority; critical for feature completeness (search) but requires careful crypto implementation and data migration.
3. **Observability**: High value for debugging, but can be implemented safely at any time via the decoupled Event Bus.