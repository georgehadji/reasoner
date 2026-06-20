# Neuro Memory Subsystem

Neuro is a **memory coprocessor** — a long-term memory layer that retains context across different pipeline runs. Think of it as the Reasoner's "biography": it remembers what you discussed previously and brings it back when needed.

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Neuro API Router              │
│  /recall  /learn  /audit  /sessions     │
└─────────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌───────┐     ┌─────────┐     ┌─────────┐
│  HOT  │────▶│  WARM   │────▶│  COLD   │
│(JSONL)│     │ (L1/L2) │     │ (disk)  │
└───────┘     └─────────┘     └─────────┘
```

---

## Storage Tiers

### 🔥 HOT — Recent Conversations (`sessions.py`)

- Stored as **JSONL** files in `~/.neuro/agents/<agent_id>/hot/`
- Each line is a JSON object: `{timestamp, prompt, response, metadata}`
- Search: simple string matching (fast, no embedding needed)
- Time window: typically the last N exchanges

### 🌡️ WARM — Semantic Cache (`cache.py`)

- **L1**: In-memory bundles with similarity threshold (default 0.75)
- **L2**: FAISS/annoy index on disk for larger scale
- Uses **embeddings** for semantic search
- Query → embed → similarity search → top-k results

### ❄️ COLD — Full Archive

- All historical data
- Accessible only if HOT/WARM return no results
- Usually compressed or archived

---

## API Endpoints

### `POST /neuro/recall` — "Remember..."

Triggered at the start of a pipeline run by `streaming.py`:

```python
resp = await client.post("/neuro/recall", json={
    "prompt": "Should I bootstrap or raise VC?",
    "agent_id": "conv-123",  # tenant isolation
    "max_results": 5
})
```

**Flow:**
1. **HOT search**: searches recent exchanges with string matching
2. **Embedding**: embeds the query
3. **L1/L2 search**: semantic similarity search
4. **Optional rerank**: cross-encoder for higher precision
5. **Compression**: `smart_compress()` if requested
6. Returns chunks with relevance scores

### `POST /neuro/learn` — "Learn from this..."

Triggered at the end of a pipeline run by `streaming.py`:

```python
resp = await client.post("/neuro/learn", json={
    "prompt": user_prompt,
    "response": assistant_response,
    "agent_id": "conv-123",
    "metadata": {"preset": "research-budget", "task_type": "startup_advice"}
})
```

**Flow:**
1. `SessionManager.ingest()` — writes to HOT JSONL
2. Optionally: embed and store in L1/L2 cache
3. Tenant-scoped: each `agent_id` has its own directory

### `POST /neuro/audit` — "Check this answer..."

Internal quality gate:

```python
resp = await client.post("/neuro/audit", json={
    "prompt": user_prompt,
    "draft_response": assistant_response,
    "agent_id": "conv-123"
})
```

**Flow:**
1. A reasoning provider (e.g., GPT-4o-mini) judges the draft
2. Returns: `verdict` (PASS/ENRICH/WARN/BLOCK), `confidence`, `reason`
3. If WARN/BLOCK, the pipeline can use it for fallback or retry

---

## Tenant Isolation

Every conversation has its own `agent_id` (usually the `conversation_id`):

```
~/.neuro/
└── agents/
    ├── conv-123/
    │   ├── hot/           # JSONL files
    │   ├── memory/        # L2 index
    │   └── cache/l1/      # L1 bundles
    └── conv-456/
        └── ...
```

Recall for one conversation **cannot see** data from others.

---

## Frontend Integration

The **NeuroPanel** (Sidebar → Memory tab) provides:

| Tab | Function |
|-----|----------|
| **Recall** | Search memory with a query |
| **Browse** | Paginated recent exchanges from `/neuro/sessions` |
| **Learn** | Manual "learn" button for the last user/assistant turn |

---

## Configuration

Neuro providers are configured via `~/.neuro/config.yaml` or fall back to defaults:

```yaml
reasoning:
  primary:
    provider: openrouter
    model: openai/gpt-4o-mini

embedding:
  primary:
    provider: openrouter
    model: qwen/qwen3-embedding-8b
```

Environment variables used:
- `OPENROUTER_API_KEY` — for reasoning & embedding via OpenRouter
- `PERPLEXITY_API_KEY` — only if using Perplexity native embeddings
- `NEURO_CONFIG` — path to custom config file

---

## Summary

| Function | What it does |
|----------|-------------|
| **Recall** | Brings relevant context from the past before reasoning starts |
| **Learn** | Stores the final result for future recall |
| **Audit** | Fact-checks the draft before showing it to the user |
| **Sessions** | Browse + pagination of history |
