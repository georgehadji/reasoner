# ADR-001: Hexagonal Architecture (Ports & Adapters)

**Status:** Accepted · **Date:** 2026-07-08
**Context:** Applied retroactively to the existing architecture.

## Context

The codebase grew organically with business logic, infrastructure, and API concerns increasingly coupled. Testing required live infrastructure (databases, LLM providers). Swapping implementations (e.g., SQLite → Postgres, in-memory → Redis) risked breaking callers.

## Decision

Adopt **Hexagonal Architecture (Ports & Adapters)** with three layers:

1. **Domain/Core** (`src/reasoner/core/`, `src/reasoner/domain/`) — Pure business logic. No imports from `infrastructure/` or `api/`. Defines port interfaces (`core/ports/`).
2. **Application** (`src/reasoner/application/`) — Orchestration: command handlers, event bus, workflow strategies, service ports (`application/ports/`). Depends only on core/domain.
3. **Infrastructure** (`src/reasoner/infrastructure/`) — Adapters implementing ports: LLM providers, database repos, auth stores. Depends on domain/application types.
4. **API** (`src/reasoner/api/`) — FastAPI routes, SSE streaming, middleware. Thin layer that wires application services to HTTP.

**Dependency rule:** `domain → application → core ports → infrastructure → api`. Violations are documented exceptions.

## Consequences

**Positive:**
- Swap storage backends without changing domain logic
- Test domain logic without infrastructure (mock ports)
- Clear ownership: each layer has defined responsibilities

**Negative:**
- More files and indirection for simple operations
- Some ports are 1:1 with a single adapter (over-abstraction risk)
- Pre-existing violations exist (noted in `AGENTS.md` watch-out section)

## Compliance

Enforced by an architecture fitness function in `tests/architecture/test_layer_boundaries.py` and import-linter configuration.
