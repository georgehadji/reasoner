<!-- Generated: 2026-06-08 | Files scanned: 375 | Token estimate: ~700 -->

# Architecture — Reasoner (ARA)

## System Type
Monorepo · Python backend (FastAPI) + Next.js 16 frontend + SearXNG search

## High-Level Data Flow

```
Browser (Next.js 16)
  │  SSE / WebSocket / REST
  ▼
FastAPI (uvicorn :8003)
  │
  ├─ HyperGate  ──── 5 sub-agents in parallel ──▶ TieBreaker
  │    ↓ routes to one of:
  │    DIRECT | WEB_SEARCH | PIPELINE
  │
  ├─ ARAPipeline (pipeline.py)
  │    Phase 0: Classification
  │    Phase 1: Decomposition
  │    Phase 2: Parallel Generation  (≥3 labs, cross-ecosystem)
  │    Phase 3: Critique & Pruning   (top-k retained)
  │    Phase 4: Stress Test
  │    Phase 5: Synthesis            (VERIFIED / HYPOTHESIS / UNKNOWN)
  │
  ├─ Neuro LTM   ──── recall context before run, learn after
  └─ Widgets     ──── stocks, weather, calculator, images, video
```

## Dependency Rule (Hexagonal DDD)
```
Interfaces → Infrastructure → Application → Core/Domain
Domain has zero outward deps.
Known violations: domain/preset_core.py → infrastructure.llm.registry
                  api/streaming.py → ARAPipeline directly
                  application/flows/__init__.py → api.serializers
```

## Service Boundaries
| Service | Port | Transport |
|---------|------|-----------|
| FastAPI backend | 8003 | HTTP/SSE/WS |
| Next.js frontend | 3000 | HTTP |
| SearXNG | 8080 | HTTP (Docker) |
| Neuro LTM | in-process | internal |
| Redis (optional) | 6379 | TCP |
| PostgreSQL (optional) | 5432 | TCP |

## Reasoning Methods (17)
orchestrated · debate · jury · research · scientific · socratic ·
pre-mortem · bayesian · dialectical · analogical · delphi · cove ·
sot · tot · pot · self-discover · writing

## Key Entry Points
- `asgi.py` — ASGI app for uvicorn
- `src/reasoner/api/__init__.py` — FastAPI factory, CORS, middleware, route mounts
- `src/reasoner/pipeline.py` — ARAPipeline orchestrator (~902 lines + 11 mixins)
- `ui-next/src/app/layout.tsx` — Next.js root layout
- `ui-next/src/app/chat/page.tsx` — Primary chat surface
- `src/reasoner/start_all.py` — Dev launcher (backend + frontend + SearXNG)
