# Context: Services

## Directory: `src/reasoner/application/services`

## Description
Application-specific services for rendering, routing decisions, and context formatting.

## Files
- **`__init__.py`**: Python package initialization module.
- **`adaptive_routing.py`**: Per-selection working state, kept so fallback selection can reuse the
- **`agent_results.py`**: Some methods nest the solution one level deeper.
- **`anonymous_trial_policy.py`**: Anonymous trial spend cap.
- **`api_key_service.py`**: : Longest lifetime a user may set on a key.
- **`audit_service.py`**: Audit Service — Logs query executions as domain events.
- **`augmentation_metrics.py`**: Augmentation A/B quality metrics.
- **`auth_service.py`**: Auth Service — Thin wrapper over AuthPort with caching and logging.
- **`billing_service.py`**: Billing Service — Orchestrates checkout, portal, and webhook sync.
- **`compaction_service.py`**: Application-layer compaction service.
- **`constraint_resolver.py`**: ── Default constraints ──
- **`credit_service.py`**: Credit Service — application-layer orchestrator for prepaid usage credits.
- **`data_eraser.py`**: GDPR user-data erasure service (DM3).
- **`deadletter_replay_service.py`**: Apply optional filter
- **`egress_policy.py`**: Resolve the effective watermark/provenance-scrubbing policy for a request.
- **`estimate_service.py`**: Cost/duration estimation, shared by the HTTP and MCP adapters.
- **`event_emission_service.py`**: ── Contextvar for per-run emitter injection ─────────────────────────
- **`evidence_service.py`**: EvidenceService — epistemic label promotion and provenance tracking.
- **`feedback_router.py`**: Default routing table: failure_type → RepairStrategy
- **`gate_service.py`**: HyperGate routing decision, shared by the HTTP and MCP adapters.
- **`harness_diagnosis.py`**: High fallback rate → routing problem
- **`harness_guard.py`**: Mapping of model aliases → training ecosystem (lab).
- **`harness_replay.py`**: Check which preset/phase the mutation targets
- **`health_service.py`**: Memory check
- **`idempotency.py`**: Idempotent run registration, shared by every inbound adapter.
- **`notification_subscriber.py`**: Code or resource asset facilitating system functionality.
- **`pipeline_service.py`**: ── Context Serialization ────────────────────────────────────────
- **`preset_service.py`**: Code or resource asset facilitating system functionality.
- **`prism_classifier.py`**: Prism query classifier — ports Prism's classifier.ts to Python.
- **`promotion_service.py`**: 1. Run regression gate
- **`quota_service.py`**: Quota Service — Application-layer orchestrator for usage limits.
- **`recovery_service.py`**: Service for executing recovery paths on problematic candidates.
- **`regression_gate.py`**: RegressionGate — pass/fail decision for harness mutation evaluation (#4b).
- **`role_requirements.py`**: ── Shared constraint sets ────────────────────────────────────────────────────
- **`run_metering.py`**: Code or resource asset facilitating system functionality.
- **`scorecard_service.py`**: ScorecardService — aggregates telemetry into harness-level metrics.
- **`search_service.py`**: Evict oldest if at capacity
- **`sensitivity_service.py`**: Sensitivity classifier for the cross-lingual probe (Part B).
- **`serializers.py`**: `_event` is defined in sse_utils to avoid duplication across
- **`spend_limit_service.py`**: Statuses that entitle a user to their subscription's tier. Anything else
- **`suggestions.py`**: Smart Suggestions Engine
- **`tool_schema.py`**: : Fields an agent may set. Everything else on RunRequest -- routing overrides,
- **`utility_scorer.py`**: Cold start: neutral score — new models get exploration budget
- **`watermark_service.py`**: Formats infrastructure/watermark/image/registry.py dispatches to. Kept here
- **`ws_ticket.py`**: Dev/CI: generate a random in-process secret, same posture as

## Subfolders
- **`renderers`**: CLI and web-friendly data renderers formatting pipeline outputs into rich, readable formats.
