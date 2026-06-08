<!-- Generated: 2026-06-08 | Files scanned: 375 | Token estimate: ~600 -->

# Data Architecture

## Storage Layers

### SQLite (primary event store)
```
infrastructure/persistence/event_store.py
  table: pipeline_events   → id, pipeline_id, event_type, payload JSON, timestamp
  table: snapshots         → pipeline_id, state JSON, version, timestamp
  Mode: WAL, connection pooling

infrastructure/persistence/feedback_store.py
  table: feedback          → pipeline_id, rating, comment, timestamp

infrastructure/persistence/auth_store.py
  table: users / tokens    → local auth fallback (dev mode)
```

### PostgreSQL (production optional)
```
infrastructure/persistence/postgres_store.py  → asyncpg, async queries
infrastructure/persistence/quota_repo_postgres.py
  table: quotas            → user_id, used_tokens, limit, period_start
infrastructure/persistence/subscription_repo.py
  table: subscriptions     → user_id, stripe_subscription_id, plan, status
Migrations: alembic/ (SQLAlchemy 2.0 async)
```

### Redis (optional cache layer)
```
infrastructure/redis/client.py     → Redis client init
infrastructure/redis/run_state.py  → pipeline run state cache (TTL-based)
Used for: active run deduplication, session state across instances
```

### Token Cache (in-process)
```
token_cache.py              → L1 memory dict (hot), L2 disk JSON (warm)
src/reasoner/cache/         → on-disk token cache files
Key: hash(prompt+model+params) → value: LLMResponse
```

### Neuro Long-Term Memory
```
neuro/server.py             → FastAPI sub-app mounted at /neuro
neuro/cache.py              → L1 memory + L2 disk + L3 embedding search
neuro/sessions.py           → session management
neuro/compression.py        → smart_compress(text, ext, level) — Aggressive/Minimal
Storage: ~/.neuro/agents/<agent_id>/  (JSONL)
Tenant: isolated by agent_id field
```

### IndexedDB (browser)
```
ui-next/src/lib/db.ts       → idb v8 wrapper
  store: conversations      → { id, messages[], preset, createdAt, updatedAt }
  store: settings           → user preferences
Zustand store hydrates from IndexedDB on mount
```

## Key Domain Models
```
models.py — PipelineState (~60 fields, Pydantic v2)
  ├─ problem, preset, method
  ├─ phase_results: dict[str, Any]   → phase outputs
  ├─ perspectives: list[str]
  ├─ critiques: list[dict]
  ├─ synthesis: str
  ├─ cost_tracking: CostTrackingState
  └─ conversation: ConversationState

core/aggregates/             → PipelineAggregate (event-sourced replay)
core/events/                 → DomainEvent hierarchy + make_event() factory
domain/preset_core.py        → PipelinePreset dataclass (routing config)
domain/preset_registry.py    → 42 preset configs
```

## File Uploads
```
uploader.py               → PDF (pypdf/pymupdf), DOCX (python-docx), images
documents/vector_store.py → simple document vector store
src/reasoner/uploads/     → uploaded file staging dir
```

## Pipeline Owner Tracking
```
history/pipeline_owners.json → maps pipeline_id → owner_token (runtime)
api/history.py               → ownership enforcement on history access
```
