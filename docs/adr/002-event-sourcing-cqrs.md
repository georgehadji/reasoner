# ADR-002: Event Sourcing + CQRS (Lightweight)

**Status:** Accepted · **Date:** 2026-07-08
**Context:** Applied retroactively to the existing architecture.

## Context

The pipeline produces many observable events (phase starts, completions, failures, LLM calls). These were historically logged ad-hoc. No single source of truth existed for replay or audit. Command and query responsibilities were mixed in handlers.

## Decision

Adopt a **lightweight Event Sourcing + CQRS pattern**:

**Event Sourcing:**
- All domain events inherit from a frozen `DomainEvent` dataclass
- Events are published to an in-memory `EventBus` with optional persistence to an `EventStore` (SQLite/Postgres)
- An event registry (`EVENT_CLASSES`) maps event types to dataclasses for type-safe replay
- Critical events are flagged via `is_critical` for priority processing

**CQRS:**
- Commands (`application/commands/`) and queries (`application/queries/`) are separated dataclass hierarchies
- Command handlers in `application/handlers/` process commands and emit events
- The hot path (SSE streaming) bypasses the CQRS layer for latency — this is a documented exception

## Consequences

**Positive:**
- Audit trail: every significant state change is recorded
- Debuggability: replay events to reconstruct pipeline state
- Clear write-vs-read separation

**Negative:**
- Additional indirection: commands routed through handler registry
- In-memory EventBus is not durable — events lost on crash unless persisted
- Hot path bypass means some events are not routed through commands
