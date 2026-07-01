# Agent-Ready Reasoner — Implementation Plan

**Date:** 2026-07-01  
**Status:** Draft  
**Scope:** Make Reasoner callable by AI agents (Claude Code, Cursor, LangChain, CrewAI, custom agents) via API key auth, sync mode, and OpenAPI schema

---

## 0. Problem Statement

Reasoner is currently a **human-facing web app** with these agent-hostile characteristics:

1. **CSRF token gate.** Every state-changing request requires fetching `/api/csrf` first — a browser security pattern that forces agents to make two round-trips.
2. **SSE-only output.** The pipeline returns a streaming `text/event-stream` that agents must parse, buffer, and reassemble. No synchronous "fire-and-forget" mode exists.
3. **Undiscoverable API.** While FastAPI auto-generates `/docs`, there's no structured tool schema (OpenAPI function-calling, MCP, or JSON Schema tool definitions) that agents can auto-discover programmatically.
4. **No API key auth.** The existing auth system (JWT + legacy API key) is wired through `Depends()` per-route — there's no middleware-level API key check that agents can use without going through the full user auth flow.

## 1. Architecture Principles

1. **Backward compatible.** Existing `/api/run` route remains unchanged. New endpoints are additive.
2. **Single source of truth.** API key validation reuses the existing `AuthManager` — no duplicate key store.
3. **Minimal new code.** Leverage FastAPI's built-in dependency injection, Pydantic schemas, and OpenAPI generation.
4. **CSRF bypass only for authenticated callers.** Unauthenticated requests still require CSRF (web security).
5. **Async-first.** Sync endpoint collects SSE internally, returns one JSON response. No blocking wrappers.
6. **Tool-schema generated from existing schemas.** Don't redefine — extract from `RunRequest` Pydantic model.

---

## 2. Implementation Plan

### 2A — API Key Authentication (Skip CSRF)

#### Problem
Agents must make two HTTP calls (`POST /api/csrf` then `POST /api/run`) for every pipeline. With API key auth, one call suffices.

#### Design
Add a `require_api_key` FastAPI dependency that:
1. Reads `Authorization: Bearer <key>` header
2. Validates via the existing `AuthManager.authenticate()` (same code path as legacy API keys)
3. On success, injects the `APIKey` object into the request context
4. Skips CSRF validation entirely (API keys are bearer tokens — no CSRF attack vector)

**New file:** `src/reasoner/api/auth_deps.py` — add `require_api_key` function

```python
# In auth_deps.py, after existing require_csrf:

async def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> APIKey:
    """Validate API key from Authorization header. Skips CSRF entirely."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    try:
        auth_manager = get_auth_manager()
        return await auth_manager.authenticate(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

**Modified route:** `src/reasoner/api/__init__.py` — add agent endpoint

```python
@app.post("/api/agent/run")  # NEW: agent-friendly, no CSRF required
async def agent_run_pipeline(
    request: Request,
    req: RunRequest,
    api_key: APIKey = Depends(require_api_key),
    rate_limit_checked = Depends(check_rate_limit),
):
    """Run pipeline with API key auth. No CSRF token needed."""
    # Reuse the existing run pipeline logic, skipping CSRF
    return StreamingResponse(
        run_stream_cached(req, request=request, user_id=api_key.name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

#### Key design decisions
- **Reuses `AuthManager` singleton** — no new key store, no duplicate logic.
- **Separate route** (`/api/agent/run`) rather than modifying `/api/run` — backward compatible. Existing web users are unaffected.
- **Bearer token pattern** — follows RFC 6750, compatible with every HTTP client, curl, and agent framework.
- **CSRF skipped entirely** for authenticated agent requests — Bearer tokens are not vulnerable to CSRF.

#### Files touched
| File | Change | Lines |
|------|--------|-------|
| `src/reasoner/api/auth_deps.py` | Add `require_api_key` dependency | +12 |
| `src/reasoner/api/__init__.py` | Add `/api/agent/run` route | +15 |
| Total | | ~27 new lines |

---

### 2B — Synchronous (Non-Streaming) Mode

#### Problem
SSE requires agents to parse `data: {...}` lines, buffer them, handle keepalive comments, and reassemble the final result. A sync endpoint returns one JSON object.

#### Design
Add `POST /api/agent/run/sync` that:
1. Internally calls `run_stream()` through an `asyncio.Queue`
2. Collects all SSE events into a list
3. Extracts the final synthesis, errors, and citations from the collected events
4. Returns a single `RunResult` JSON response

**New file:** `src/reasoner/api/schemas.py` — add `RunResult` model

```python
class RunResult(BaseModel):
    """Aggregated pipeline result for agent consumption."""
    preset: str
    errors: list[str] = []
    total_tokens: dict[str, int] = {"input": 0, "output": 0, "total": 0}
    duration_seconds: float = 0.0
    synthesis: str = ""           # core_solution text
    critical_insights: list[str] = []
    open_questions: list[str] = []
    citations: list[dict] = []
    phase_durations: dict[str, float] = {}
    models_used: list[str] = []   # model IDs from phase_complete events
```

**New endpoint:** `src/reasoner/api/__init__.py`

```python
@app.post("/api/agent/run/sync", response_model=RunResult)
async def agent_run_sync(
    request: Request,
    req: RunRequest,
    api_key: APIKey = Depends(require_api_key),
    rate_limit_checked = Depends(check_rate_limit),
):
    """Run pipeline synchronously and return aggregated result JSON."""
    events: list[dict] = []
    errors: list[str] = []
    
    async for sse_line in run_stream_cached(req, request=request, user_id=api_key.name):
        if sse_line.startswith("data: "):
            try:
                ev = json.loads(sse_line[6:])
                events.append(ev)
                if ev.get("type") == "error":
                    errors.append(ev.get("error", ""))
            except json.JSONDecodeError:
                pass

    # Extract synthesis from the last phase_complete with core_solution
    synthesis = ""
    for ev in reversed(events):
        if ev.get("type") == "phase_complete":
            data = ev.get("data", {})
            core = data.get("core_solution", "")
            if core:
                synthesis = core
                break

    done = next((e for e in events if e.get("type") == "done"), {})
    
    return RunResult(
        preset=req.preset,
        errors=errors,
        total_tokens=done.get("total_tokens", {}),
        duration_seconds=done.get("duration", 0),
        synthesis=synthesis,
        critical_insights=done.get("critical_insights", []),
        open_questions=done.get("open_questions", []),
        citations=done.get("citations", []),
        phase_durations=done.get("phase_durations", {}),
        models_used=list({
            m for e in events if e.get("type") == "phase_complete"
            for m in e.get("data", {}).get("models", [])
        }),
    )
```

#### Key design decisions
- **Internally uses the same `run_stream_cached()` generator** — identical logic, same caching, same error handling.
- **Blocking from the agent's perspective** — the HTTP response only arrives when the pipeline completes.
- **Pydantic `response_model`** auto-generates OpenAPI schema — agents can discover the response shape.
- **Timeout:** Uses the existing SSE timeout chain (phase-level timeouts). The HTTP connection stays open until done.

#### Files touched
| File | Change | Lines |
|------|--------|-------|
| `src/reasoner/api/schemas.py` | Add `RunResult` model | +15 |
| `src/reasoner/api/__init__.py` | Add `/api/agent/run/sync` route | +45 |
| Total | | ~60 new lines |

---

### 2C — OpenAPI Schema & Tool Definition

#### Problem
FastAPI auto-generates `/docs` but agents need a **structured tool schema** they can parse programmatically — typically JSON Schema function definitions or OpenAPI tool specs.

#### Design
Three additive changes:

**C1: Enhance OpenAPI metadata.** Add tags, descriptions, and server info to the FastAPI app constructor so auto-generated docs are more useful.

**C2: Add `/openapi.json` tool-compatible schema.** FastAPI already generates this at `/openapi.json` — zero code needed. Agents that speak OpenAPI (LangChain, CrewAI) can discover it automatically. Document this.

**C3: Add a compact tool-schema endpoint.** `GET /api/agent/tools` returns a minimal JSON array of function definitions (OpenAI function-calling format) for the agent-facing endpoints only — `/api/agent/run`, `/api/agent/run/sync`, `/api/agent/search`, `/api/health`.

```python
@app.get("/api/agent/tools")
async def agent_tools():
    """Return compact function-calling schema for agent consumption."""
    return [
        {
            "name": "reasoner_run",
            "description": "Run a multi-model reasoning pipeline on a problem. Returns SSE stream.",
            "endpoint": "POST /api/agent/run",
            "parameters": {
                "problem": {"type": "string", "required": True, "description": "The problem or question to reason about"},
                "preset": {"type": "string", "required": False, "default": "auto-budget", "description": "Pipeline preset name (e.g. scientific-budget, bayesian-premium)"},
                "top_k": {"type": "integer", "required": False, "default": 2},
                "source_type": {"type": "string", "required": False, "enum": ["general", "academic", "news"]},
            },
            "auth": "Bearer API key in Authorization header",
        },
        {
            "name": "reasoner_run_sync",
            "description": "Run pipeline and return aggregated JSON result (non-streaming).",
            "endpoint": "POST /api/agent/run/sync",
            "parameters": {
                "problem": {"type": "string", "required": True, "description": "The problem or question to reason about"},
                "preset": {"type": "string", "required": False, "default": "auto-budget"},
                "top_k": {"type": "integer", "required": False, "default": 2},
            },
            "auth": "Bearer API key in Authorization header",
        },
        {
            "name": "reasoner_health",
            "description": "Check if Reasoner is running and healthy.",
            "endpoint": "GET /api/health",
            "parameters": {},
            "auth": "None",
        },
    ]
```

#### Key design decisions
- **Derived from existing schemas** — `RunRequest` fields are the source of truth; the tool schema is a projection.
- **Manual endpoint** rather than auto-generated from OpenAPI — gives control over which endpoints agents see and how they're described.
- **Follows OpenAI function-calling format** — directly consumable by Claude, GPT, LangChain, CrewAI.

#### Files touched
| File | Change | Lines |
|------|--------|-------|
| `src/reasoner/api/__init__.py` | Add `agent_tools` endpoint + enhance FastAPI constructor | +50 |
| Total | | ~50 new lines |

---

## 3. Implementation Order

| # | Feature | Files | Lines | Risk | Dependency |
|---|---------|-------|-------|------|-----------|
| **1** | 2A — API key auth + agent run endpoint | `auth_deps.py`, `__init__.py` | ~27 | Low | None |
| **2** | 2B — Sync mode + RunResult schema | `schemas.py`, `__init__.py` | ~60 | Low | 2A (needs require_api_key) |
| **3** | 2C — Tool schema endpoint + OpenAPI docs | `__init__.py` | ~50 | Low | 2A (documents new endpoints) |

**Total: ~137 new lines across 3 files. Zero existing code paths modified.**

---

## 4. Agent Usage Examples

### Claude Code / Cursor (direct HTTP)

```python
import httpx, json

async with httpx.AsyncClient() as client:
    r = await client.post(
        "http://localhost:8003/api/agent/run/sync",
        json={
            "problem": "What are the latest breakthroughs in fusion energy?",
            "preset": "research-premium",
        },
        headers={"Authorization": "Bearer sk-..."},
        timeout=300,
    )
    result = r.json()
    print(result["synthesis"])
    print(result["citations"])
```

### LangChain Tool

```python
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

class ReasonerInput(BaseModel):
    problem: str = Field(description="The problem to reason about")
    preset: str = Field(default="scientific-budget")

async def reasoner_tool(problem: str, preset: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8003/api/agent/run/sync",
            json={"problem": problem, "preset": preset},
            headers={"Authorization": f"Bearer {REASONER_API_KEY}"},
            timeout=300,
        )
        return r.json()["synthesis"]

tool = StructuredTool.from_function(
    name="reasoner",
    description="Research and reason about complex topics using multi-model pipelines",
    func=reasoner_tool,
    args_schema=ReasonerInput,
)
```

### curl (one-liner)

```bash
curl -s -X POST http://localhost:8003/api/agent/run/sync \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{"problem": "Why is the sky blue?", "preset": "scientific-budget"}' \
  | jq '.synthesis'
```

---

## 5. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| API key authentication reuse | Uses existing `AuthManager.authenticate()` — same key validation as legacy API keys. Keys are SHA-256 hashed in storage. |
| Rate limiting for agents | Existing `check_rate_limit` dependency already applied to the new agent routes. Agents with valid API keys get rate-limit tiers from their key config. |
| CSRF bypass safety | Only allowed for `Authorization: Bearer` requests — Bearer tokens cannot be set by cross-origin scripts, making CSRF impossible. |
| No key, no entry | Unauthenticated requests to `/api/agent/*` return 401. No CSRF fallback for agent endpoints. |
| Key generation | Existing `POST /api/keys/generate` (if exposed) creates keys with scopes and expiry. Agents use viewer/user/admin scopes. |

---

## 6. Testing Plan

| Test | Type | What it verifies |
|------|------|-----------------|
| `test_agent_api_key_auth` | Unit | `require_api_key` returns 401 without header, 401 with invalid key, 200 with valid key |
| `test_agent_sync_run` | Integration | `POST /api/agent/run/sync` returns `RunResult` with synthesis, citations, models_used |
| `test_agent_tools_schema` | Unit | `GET /api/agent/tools` returns valid JSON array with expected function definitions |
| `test_agent_csrf_bypass` | Integration | Agent endpoints work WITHOUT `X-CSRF-Token` header |
| `test_agent_streaming` | Integration | `POST /api/agent/run` returns SSE stream identical to `/api/run` |
| `test_backward_compat` | Regression | `POST /api/run` still requires CSRF, still works for web users |

---

## 7. Rollback

All changes are additive (new routes, new dependencies, new model). Rolling back is one revert commit. Existing `/api/run`, `/api/health`, and all other routes are untouched.

---

## 8. Definition of Done

- [ ] `POST /api/agent/run` accepts `Authorization: Bearer <key>`, returns SSE stream
- [ ] `POST /api/agent/run/sync` returns `RunResult` JSON with synthesis, citations, models
- [ ] `GET /api/agent/tools` returns function-calling schema
- [ ] All existing tests pass (no regressions)
- [ ] New tests cover auth, sync, streaming, and CSRF bypass paths
- [ ] `curl` one-liner in section 4 works end-to-end
- [ ] OpenAPI `/docs` shows new agent endpoints under "Agent" tag

---

## 9. Files Summary

| File | Change | Lines |
|------|--------|-------|
| `src/reasoner/api/schemas.py` | Add `RunResult` model | +15 |
| `src/reasoner/api/auth_deps.py` | Add `require_api_key` dependency | +12 |
| `src/reasoner/api/__init__.py` | Add `/api/agent/run`, `/api/agent/run/sync`, `/api/agent/tools`, FastAPI tags | +105 |
| `tests/test_agent_integration.py` | New test file | +60 |
| Total | | ~192 lines |
