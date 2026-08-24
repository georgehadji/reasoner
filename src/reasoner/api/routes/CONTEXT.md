# Context: Routes

## Directory: `src/reasoner/api/routes`

## Description
The distinct REST and SSE endpoint routers (e.g. running, configuration, billing, neuro states).

## Files
- **`account_keys.py`**: User-owned API key management endpoints.
- **`admin.py`**: Admin endpoints — manual operations requiring ADMIN_API_KEY authentication.
- **`agent.py`**: ── Tool discovery ──────────────────────────────────────────────────
- **`context.py`**: Resolve preset and build router via orchestrator
- **`credits.py`**: Credit balance, ledger, and administrative grant endpoints.
- **`errors.py`**: Error reporting and admin error log endpoints.
- **`estimate.py`**: Cost estimate endpoint — POST /api/estimate.
- **`feedback.py`**: Feedback and admin feedback stats endpoints.
- **`gate.py`**: HyperGate routing endpoint — POST /api/gate.
- **`gdpr.py`**: GDPR data erasure endpoint (DM3).
- **`health.py`**: Health check endpoint — /api/health.
- **`history.py`**: Search history endpoints.
- **`images.py`**: Code or resource asset facilitating system functionality.
- **`keys.py`**: SECURITY: Admin-only endpoint to prevent reconnaissance.
- **`legacy_widgets.py`**: Legacy widget endpoints (weather, stocks, calculator, discover).
- **`pipelines.py`**: Admins can access any pipeline
- **`provenance.py`**: Text inspect/scrub is O(length) over a fixed carrier alphabet -- generous,
- **`telemetry.py`**: Telemetry API routes — read-only harness metrics.
- **`uploads.py`**: Reject oversized multipart bodies before Starlette parses them into
- **`websocket.py`**: Code or resource asset facilitating system functionality.
- **`widgets.py`**: SECURITY: Do not expose supported methods or presets

## Subfolders
*No subfolders in this directory.*
