# Context: Architecture

## Directory: `tests/architecture`

## Description
Automated tests asserting code structural invariants (e.g. no core importing infrastructure, dependency lines).

## Files
- **`test_domain_modules.py`**: Unknown values coerce without raising; fallback is an existing member
- **`test_event_emission.py`**: Integration tests for event emission via EventEmissionService (Phase 3.1 / CE 1.1).
- **`test_integration_events.py`**: ── Mock Router ─────────────────────────────────────────────────────
- **`test_layer_boundaries.py`**: Architectural fitness functions — enforce dependency direction.
- **`test_models_split.py`**: Tests for PipelineState decomposition — backward compat and new paths.
- **`test_regression_bugs.py`**: Regression tests for bug fixes (v3.1 SRE audit).
- **`test_sse_events.py`**: ── SSE EVENT TYPE CATALOG ──────────────────────────────────────────

## Subfolders
*No subfolders in this directory.*
