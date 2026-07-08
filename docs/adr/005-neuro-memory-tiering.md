# ADR-005: Neuro Memory Tiering

**Status:** Accepted · **Date:** 2026-07-08
**Context:** Implemented as part of pipeline v2.

## Context

The pipeline generates significant context per run (conversation history, intermediate results, final syntheses). Re-using this context across runs improves quality (continuity, learning from past mistakes). Storing everything in memory is expensive; storing only in persistent storage is slow.

## Decision

Implement a **three-tier memory system** (L1/L2/L3):

1. **L1 (Hot)** — In-memory dict per active agent. Fastest access, lost on restart.
2. **L2 (Warm)** — JSON files on disk per agent. Survives restart, moderate access speed.
3. **L3 (Cold)** — Embedding-based retrieval via Neuro server. Slower but supports semantic search across all agents.

**Lifecycle:** Hot sessions are archived to warm after inactivity (30min TTL). Warm sessions are pruned to cold (LRU-based). Cold embeddings are searched at pipeline preflight.

**Tenant isolation:** Each `agent_id` maps to a separate data directory (`~/.neuro/agents/<id>/`).

## Consequences

**Positive:**
- Hot cache provides fast recall for active conversations
- Cold store supports cross-session semantic search
- LRU eviction prevents unbounded memory growth

**Negative:**
- Three-tier adds architectural complexity
- L1/L2 data can become stale if not archived correctly (mitigated by TTL + cron lifecycle)
- Cold retrieval adds latency to preflight (5s timeout applied)
