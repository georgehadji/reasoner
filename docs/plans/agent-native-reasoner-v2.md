# Agent-Native Reasoner — Implementation Plan (v2)

**Date:** 2026-08-15
**Status:** Draft for review
**Branch target:** `feat/agent-native`
**Supersedes:** [`agent-ready-reasoner.md`](agent-ready-reasoner.md) (2026-07-01, shipped — its endpoints exist and are the subject of Workstream 1)

**Scope:** close the four gaps that stop Reasoner from being credibly marketable as agent-consumable infrastructure:

1. the agent endpoints authenticate against the wrong key store and are not credit-metered;
2. they are unreachable on the hosted deployment (no Next proxy route);
3. the tool-discovery endpoint is neither discoverable nor in a standard schema format;
4. there is no MCP server, and the TypeScript SDK is unpublished.

---

## 0. Verified starting state

Every claim below was read out of the tree on 2026-08-15, not inferred.

| Fact | Evidence |
| --- | --- |
| `/api/agent/run`, `/api/agent/run/sync`, `/api/agent/tools` exist | `src/reasoner/api/__init__.py:603-715` |
| They authenticate via `require_api_key` → legacy `AuthManager`, a *different* key store from `rsn_live_` account keys | `src/reasoner/api/auth_deps.py:145`, `src/reasoner/infrastructure/auth_legacy.py:75-183` |
| They carry no quota, credit, or settlement dependency — runs through them are free | `src/reasoner/api/__init__.py:645-715` (compare `:721-774`) |
| `/api/run` already exempts valid API keys from CSRF, so the "agent needs a CSRF-free route" premise is obsolete | `src/reasoner/api/auth_deps.py:203-241` |
| Credit settlement is inlined in the HTTP layer, reachable only from `/api/run` | `src/reasoner/api/__init__.py:489-591` |
| Event→result aggregation already lives in the application layer | `src/reasoner/application/services/agent_results.py:42-89` |
| The Next.js proxy has no `agent/` route; only the listed `src/app/api/*` paths exist | `ui-next/src/app/api/` |
| The proxy forwards `Authorization` and can stream an upstream body verbatim | `ui-next/src/lib/security-server.ts:137-158`, `ui-next/src/app/api/run/route.ts:38-53` |
| `/api/agent/tools` is `POST` and `include_in_schema=False`; its payload is not OpenAI/Anthropic tool format | `src/reasoner/api/__init__.py:608-642` |
| A pipeline is hard-capped at 600s | `src/reasoner/core/constants_limits.py:330` |
| The SSE wire contract is a tested artefact | `sdk/contract/events.json`, `tests/test_sdk_contract.py` |
| The TS SDK is complete but `"private": true` | `sdk/typescript/package.json` |
| Layer order for import-linter — `reasoner.api` is the outermost layer | `.importlinter:12-25` |

**The load-bearing conclusion:** there is no missing *capability*. There is one duplicated inbound path (`/api/agent/*`) that bypasses the metering the real path performs, and no adapter for the protocol agents actually speak (MCP). The work is consolidation plus one new driving adapter — not new domain logic.

---

## 1. Architecture principles for this change

1. **One pipeline entry, many driving adapters.** HTTP-SSE, HTTP-sync, and MCP are *inbound adapters* in the hexagonal sense. Each translates a protocol into the same application-layer call. None may re-implement metering, aggregation, or routing.
2. **Metering belongs to the application layer, not to FastAPI.** Anything that only `/api/run` does today, and that a second adapter would have to copy, is misplaced. Move it once; adapters compose it.
3. **Respect the layer contract.** New modules obey `.importlinter:12-25`. `reasoner.api.mcp` is legal (api is the outermost layer). `reasoner.application.services.*` may not import `reasoner.api`.
4. **Additive, then subtractive behind a flag.** Existing routes keep working; the legacy behaviour goes behind `ENABLE_LEGACY_AGENT_API`, defaulted `false` for new deployments and documented in `.env.example` for self-hosters mid-upgrade.
5. **Functional core, imperative shell.** Event folding, schema projection, and cost extraction are pure functions over plain data — trivially testable, no I/O. Adapters are the only things that touch the network, the clock, or the ledger.
6. **The contract file is the SSOT.** `sdk/contract/events.json` already binds backend and SDK. New surfaces (tool schema, MCP tool list) get the same treatment: a generated artefact plus a test asserting the code still produces it.
7. **No second key store.** Every new surface authenticates through `get_current_user` (account keys + JWT). The legacy `AuthManager` is not extended.

### Paradigm per module

| Module | Paradigm | Primary patterns | Rationale |
| --- | --- | --- | --- |
| `application/services/run_metering.py` (new) | Functional core + async generator pipeline | **Decorator** over `AsyncIterator[str]`; **Strategy** for the settlement sink | Metering is a cross-cutting concern over a stream; a decorator adds it without any adapter knowing how credits work |
| `application/services/agent_results.py` (extend) | Pure functional | **Fold/Reducer**; **Value Object** (`RunSummary`) | Aggregation is a deterministic function of an event list — no state, no I/O, exhaustive unit tests |
| `application/services/tool_schema.py` (new) | Declarative + pure | **Projection / Anti-corruption layer**; **Registry** of tool descriptors | Derive from `RunRequest` rather than restating it, so the schema cannot drift from the model |
| `api/routes/agent.py` (new) | OO adapter, DI-driven | **Adapter**; **Facade**; FastAPI **Dependency Injection** | Thin translation from HTTP to application calls |
| `api/mcp/` (new package) | OO adapter + Command | **Adapter**; **Command** onto existing CQRS handlers; **Observer** for progress notifications | MCP is another driving port; its tools map 1:1 onto commands/queries that already exist |
| `ui-next/src/app/api/agent/**` | Functional route handlers | **Proxy**; **Chain of validation** (reuses `security-server.ts` primitives) | Matches the existing route style; no new abstraction |
| `sdk/typescript` | Functional + typed | **Facade** (`ReasonerClient`); **Iterator adapter** (`parseSSE`) | Already correct; only packaging changes |

---

## 2. Workstream 0 — Foundation: extract the metered run

**Problem.** `_extract_run_cost`, `_settle_run_credits`, the Prometheus counters, and the try/finally that ties them to the stream all live inside `api/__init__.py:489-591`, wrapped around `run_stream_cached`. Any second adapter either copies ~60 lines of settlement logic or silently gives runs away — which is exactly what `/api/agent/run` does today.

**Design.** A metered run is the composition of two pure functions and one effectful sink:

```
run_stream_cached(req) ──▶ metered(stream, ctx, sink) ──▶ AsyncIterator[str]
                              │
                              ├─ pure:  extract_run_cost(frame) -> float | None
                              └─ sink:  SettlementSink.settle(user_id, cost, ref, preset)
```

**New file:** `src/reasoner/application/services/run_metering.py`

```python
"""Metering decorator shared by every inbound adapter that runs a pipeline.

The pipeline is billed post-paid from the `total_cost_usd` on its terminal
`done` frame, so metering is naturally a *wrapper around the stream* rather
than a step before or after it. Keeping it here — not in the HTTP layer —
is what stops a second adapter (sync endpoint, MCP tool) from quietly
running pipelines for free.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class SettlementSink(Protocol):
    async def settle(self, *, user_id: str, cost_usd: float,
                     reference_id: str, preset: str) -> None: ...


class RunObserver(Protocol):
    def observe(self, *, status: str) -> None: ...


@dataclass(frozen=True)
class RunContext:
    user_id: str | None      # None => unauthenticated/legacy, nothing to charge
    preset: str
    reference_id: str
    tier: str
    interface: str           # "web" | "agent_http" | "agent_sync" | "mcp"


def extract_run_cost(frame: str) -> float | None:
    """Pure. Moved verbatim from api/__init__.py::_extract_run_cost."""


async def metered(
    stream: AsyncIterator[str],
    ctx: RunContext,
    sink: SettlementSink,
    observer: RunObserver | None = None,
) -> AsyncIterator[str]:
    """Yield every frame untouched; settle once the stream terminates.

    Settlement runs in `finally` so a client disconnect mid-run still bills
    the work already performed, and never raises — the answer is already
    delivered, so a ledger outage is reconciled later, not surfaced as a
    stream error.
    """
```

- `SettlementSink` is a `Protocol`, so tests inject a recording double and never touch the credit service.
- `RunObserver` carries the Prometheus counter out of the HTTP layer, so MCP runs land in the same metrics with a different `interface` label.
- `api/__init__.py::_run_stream_with_metrics` collapses into a call to `metered(...)` with a `CreditServiceSink` adapter. Net line count falls.

**Extend:** `src/reasoner/application/services/agent_results.py`

Add the fold that `agent_run_sync` performs inline today at `api/__init__.py:684-715`:

```python
@dataclass(frozen=True)
class RunSummary:
    preset: str
    method: str | None
    synthesis: str
    critical_insights: tuple[str, ...]
    open_questions: tuple[str, ...]
    claim_labels: Mapping[str, str]
    action_blueprint: tuple[Mapping[str, str], ...]
    citations: tuple[Mapping[str, Any], ...]
    models_used: tuple[str, ...]
    total_tokens: Mapping[str, int]
    total_cost_usd: float
    duration_seconds: float
    errors: tuple[str, ...]


def summarise(events: Sequence[Mapping[str, Any]], *, preset: str) -> RunSummary: ...
```

Immutable by construction (`frozen=True`, tuples not lists) per the project's immutability rule. `RunResult` (`api/schemas.py:301`) becomes a projection of `RunSummary` and gains the fields the fold already recovers but currently drops: `claim_labels`, `action_blueprint`, `method`, `total_cost_usd`. `model_config = {"extra": "forbid"}` stays. `sdk/contract/events.json:112-127` (`expected_summary`) is the naming reference, so Python and TypeScript agree field-for-field.

**Tests (write first).**

| Test | Asserts |
| --- | --- |
| `tests/test_run_metering.py::test_settles_from_done_frame` | One `settle` call with the exact `total_cost_usd` |
| `…::test_settles_on_client_disconnect` | Generator closed early → still settles the frames seen |
| `…::test_never_raises_on_sink_failure` | Sink raises → stream completes, warning logged |
| `…::test_anonymous_context_never_settles` | `user_id=None` → zero sink calls |
| `tests/test_agent_results.py::test_summarise_*` | Last synthesis wins; citations from their own frame; crashed run yields empty synthesis with populated errors |

**Files touched:** 2 new, 3 modified. ~180 added / ~70 removed.
**Risk:** low — behaviour-preserving refactor, with the existing `/api/run` integration tests as the safety net.

---

## 3. Workstream 1 — Hosted agent endpoints, metered and reachable

### 1A. Backend: consolidate onto account keys

**New file:** `src/reasoner/api/routes/agent.py` — moves the three endpoints out of `api/__init__.py` (a 1000-line app factory that should not also host route bodies) and rebuilds them on the correct dependency chain.

```python
router = APIRouter(prefix="/api/agent", tags=["Agent"])

@router.post("/run")                                   # SSE, metered
async def agent_run(
    request: Request,
    req: RunRequest,
    user: User = Depends(get_current_user),            # account key OR JWT
    _rl = Depends(check_rate_limit),
    _quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    _credits = Depends(require_credits_if_authenticated),
    preset_service: PresetService = Depends(get_preset_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> StreamingResponse: ...

@router.post("/run/sync", response_model=RunResult)    # blocking JSON, metered
async def agent_run_sync(...) -> RunResult: ...

@router.get("/tools")                                  # see Workstream 2
async def agent_tools(format: str = "anthropic") -> list[dict]: ...
```

Design decisions:

- **`get_current_user`, not `require_api_key`.** One key store, real ownership, real credits. `require_api_key` and the legacy `AuthManager` stay in the tree for the self-hosted path but stop being the agent story.
- **`/run/sync` reuses `metered(...)` and `summarise(...)`.** It consumes its own SSE stream internally, exactly as today, but through the shared decorator — so a sync run is billed identically to a streaming one, with no duplicated settlement code.
- **Idempotency parity.** `/run` and `/run/sync` both register `client_run_id` through `_run_state_manager` (the guard at `api/__init__.py:741-763`). Extract that block into `application/services/idempotency.py::register_run(client_run_id)` so all three call sites share one implementation and one 409 semantic. Agents retry far more than humans; this is the highest-value robustness item in the plan.
- **Ownership.** Agent-started runs get the same `pipeline_ownership_repo` record as UI runs, so `GET /api/pipelines/{id}` fails closed for other users (`api/routes/pipelines.py:21-51`).
- **Legacy compatibility.** The old handlers move behind `settings.ENABLE_LEGACY_AGENT_API`; when true, `require_api_key`-authenticated calls are accepted on the same paths and marked `deprecated=True` in OpenAPI.

### 1B. Frontend proxy: make them reachable on the hosted domain

**New:** `ui-next/src/app/api/agent/run/route.ts` (SSE passthrough) and `ui-next/src/app/api/agent/run/sync/route.ts` (JSON).

Both follow `ui-next/src/app/api/run/route.ts` exactly: `rateLimit` → validate → `validateUpstreamUrl(getApiBaseUrl())` → `sanitizeRequestHeaders` (already allowlists `authorization`) → `fetch` → return `upstream.body` with `sanitizeResponseHeaders`.

One deliberate divergence: **these routes do not call `requireCsrfToken`.** They are bearer-only. Enforce that explicitly rather than by omission:

```ts
const auth = req.headers.get('authorization') ?? '';
if (!auth.toLowerCase().startsWith('bearer ')) {
  return NextResponse.json(
    { error: 'Agent endpoints require Authorization: Bearer <api key>' },
    { status: 401 },
  );
}
```

Without that guard the routes would be a browser-reachable, CSRF-free path to a metered endpoint — precisely the hole CSRF exists to close. The backend would still reject the call, but a proxy should not forward a request it already knows is invalid, and the explicit check documents the intent for the next reader.

Also:

- add `AGENT_RUN: '/api/agent/run'` and `AGENT_RUN_SYNC: '/api/agent/run/sync'` to `ui-next/src/lib/config.ts` (~line 210) — every `API.*` constant needs a matching route file or it 404s;
- add an `agentRun` bucket to `RATE_LIMITS` in `security-server.ts`, more permissive per-IP than `run` (agents are servers, not tabs) but still bounded;
- reuse `validateRunRequest` unchanged.

**Timeout reality check.** A sync run can legitimately take 600s (`constants_limits.py:330`), and Node/serverless hosts commonly cap a route well below that. Therefore:

- the streaming route is the **recommended** hosted path and must be documented as such;
- the sync route sets the platform maximum (`export const maxDuration = 800` where supported) and, on timeout, returns **504 with the `client_run_id` in the body**, so the caller recovers the completed run from history instead of re-running and re-paying;
- if the deployment target cannot exceed the pipeline cap, ship the sync route **self-hosted-only** and say so in the docs, rather than shipping an endpoint that dies at minute five. Decide this against the actual host before merging 1B.

### 1C. Docs follow-through

`ui-next/src/lib/docs.ts` → the `agent-integration` page currently states that the hosted API has no blocking endpoint and that `/api/agent/*` is self-hosted only. **Both statements become false when 1A+1B merge.** Update in the same PR: the "Read the stream" and "Self-hosted deployments" sections, plus the `api-reference` catalogue table. Add `tests/test_docs_endpoint_drift.py`, failing when a path string in `docs.ts` has no corresponding FastAPI route — documentation drift is how an "agent-ready" claim becomes a support ticket.

**Files touched:** 3 new backend, 2 new frontend, ~6 modified. ~420 added.
**Risk:** medium — touches billing. Mitigated by Workstream 0's tests plus an end-to-end test asserting one `/api/agent/run/sync` call debits the ledger exactly once.

---

## 4. Workstream 2 — Tool schema that agents can actually consume

**Problems with the current endpoint** (`api/__init__.py:608-642`): it is `POST` (discovery should be idempotent and cacheable), `include_in_schema=False` (invisible in `/openapi.json`), hand-written (drifts from `RunRequest`), and its `parameters` object is not JSON Schema — so no framework registers it without a shim.

**New file:** `src/reasoner/application/services/tool_schema.py`

```python
"""Function-calling schemas projected from the Pydantic request models.

Hand-maintained tool schemas drift the first time a field is added to
RunRequest. These are generated from `RunRequest.model_json_schema()` and
narrowed by an explicit allowlist, so a new field stays invisible to agents
until someone deliberately exposes it — the correct default for a public
tool surface.
"""

AGENT_FIELDS = ("problem", "preset", "top_k", "web_search", "source_type", "client_run_id")


@lru_cache(maxsize=1)
def tool_definitions() -> tuple[ToolDefinition, ...]: ...


def as_anthropic(defs: Sequence[ToolDefinition]) -> list[dict]:  # {name, description, input_schema}
def as_openai(defs: Sequence[ToolDefinition]) -> list[dict]:     # {type: "function", function: {...}}
```

`ToolDefinition` is a frozen dataclass — name, description, JSON Schema, and hints (`readOnlyHint` for `gate`/`estimate`/`presets`; a cost hint for `run`). Two thin serialisers over one source of truth. The `lru_cache` is safe: the schema is a pure function of imported models.

**Endpoint:** `GET /api/agent/tools?format=anthropic|openai` (default `anthropic`), `include_in_schema=True`, `Cache-Control: public, max-age=3600`, strong `ETag` from a hash of the payload. The `POST` alias remains for one version, `deprecated=True`, returning an identical body.

**Tools exposed:** `reasoner_run`, `reasoner_run_sync`, `reasoner_gate`, `reasoner_estimate`, `reasoner_presets`, `reasoner_health`. Descriptions carry the guidance the docs page already codifies — what the tool is for, that a run takes 20–90s, that it costs money — because a tool description is the only prompt the calling model reads.

**Contract test:** `tests/test_agent_tools_contract.py` snapshots the payload to `sdk/contract/tools.json` (refreshed with `UPDATE_SDK_CONTRACT=1`, mirroring `tests/test_sdk_contract.py`) and asserts every exposed field exists on `RunRequest` — a rename in the model breaks the test rather than the agents.

**Files touched:** 2 new, 2 modified, 1 new contract artefact. ~200 added.
**Risk:** low, additive.

---

## 5. Workstream 3 — MCP server

The largest gap. MCP is how agent hosts discover tools in practice: an HTTP API is something an integrator wires up; an MCP server is something a user installs.

### Placement and boundaries

```
src/reasoner/api/mcp/
├── __init__.py        # build_mcp_server(settings) -> Server   (factory)
├── tools.py           # ToolSpec registry; handlers -> application services
├── resources.py       # reasoner://presets, reasoner://models, reasoner://docs
├── context.py         # per-session auth + RunContext construction
└── progress.py        # SSE frame -> MCP progress notification adapter
```

`reasoner.api.mcp` sits in the outermost layer (`.importlinter:13`), so it may import application, infrastructure, core, and domain — no contract change expected. **The rule for reviewers: nothing in `api/mcp/` may contain reasoning, routing, pricing, or aggregation logic.** It translates MCP calls into the same application calls the HTTP adapter makes. If a behaviour is needed by both, it belongs in `application/services/`.

### Tools

| MCP tool | Maps to | Notes |
| --- | --- | --- |
| `reasoner_run` | `run_stream_cached` + `metered` + `summarise` | Blocking; emits MCP progress notifications per `phase_start`/`phase_complete`; returns `RunSummary` as structured content |
| `reasoner_gate` | `HyperGateAgent.decide` (the `/api/gate` logic) | Read-only, cached, cheap — the pre-flight an agent should call first |
| `reasoner_estimate` | estimate logic (`api/routes/estimate.py`) | Read-only |
| `reasoner_followup` | `run_followup_stream` | Takes `conversation_id` + `previous_synthesis` |
| `reasoner_presets` | `PresetService` | Also exposed as a resource |

Progress reporting is why MCP beats a plain HTTP tool here: `progress.py` subscribes to the same generator the HTTP adapter yields and converts phase frames into `notifications/progress`, so the host UI shows "Phase 3: Critique" instead of a 90-second hang. That is an **Observer** over the existing stream, not a second execution path.

### Transports

- **stdio** — `mcp_server.py` at repo root (sibling of `main.py`/`asgi.py`), for Claude Desktop/Code and local agents. Auth from `REASONER_API_KEY` in the process env; when absent and the instance is local, fall back to in-process execution via `reasoner.headless` — no HTTP hop at all, and it reuses the module the README already documents.
- **Streamable HTTP** — mounted at `/mcp` on the FastAPI app behind `settings.ENABLE_MCP_HTTP` (default `false`), authenticated by the same bearer key as the REST API, so hosted users get an MCP endpoint without running a second process.

### Session, auth, and safety

- `context.py` resolves the key once per session into a `RunContext` and caches the resolved user; every tool call re-checks scope and credits through the *existing* services (not through FastAPI `Depends`, which is HTTP-bound).
- `sanitize_for_prompt()` gates `problem` exactly as the HTTP path does — the invariant in `CLAUDE.md §5` is not adapter-specific.
- No admin tool is exposed. Ever. `/api/admin/*` has no MCP counterpart, and this package's review checklist says so explicitly.
- Tool results carrying citations return the source URL as *data*, never as instruction; the server must not echo fetched page content into a field the host might treat as directive.

### Dependency and packaging

Add the official Python MCP SDK as an **optional extra**, not a base requirement:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.2,<2"]
```

`pip install reasoner[mcp]`. The base install stays lean; `api/mcp/` imports are guarded so a missing extra yields a clear startup message rather than an `ImportError` traceback.

Ship `docs/MCP.md` plus a copy-paste host config block:

```json
{
  "mcpServers": {
    "reasoner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "REASONER_API_KEY": "rsn_live_..." }
    }
  }
}
```

**Tests:** `tests/test_mcp_tools.py` — the tool list matches `sdk/contract/tools.json` where they overlap; `reasoner_run` settles credits exactly once (same `SettlementSink` double as Workstream 0); progress notifications fire per phase; a missing or invalid key yields an MCP error, not a stack trace; no admin tool is registered.

**Files touched:** ~6 new modules, 1 new root entrypoint, 1 doc, `pyproject.toml`, `.importlinter` if an exemption proves necessary. ~700 added.
**Risk:** medium — new protocol surface, but zero new business logic and it is off by default over HTTP.

---

## 6. Workstream 4 — Publish the SDK

The client is finished (`sdk/typescript/src/`, contract-tested against `events.json`); only packaging blocks it.

1. `package.json`: drop `"private": true`, set the real license, scope the name (`@reasoner/sdk` needs the npm org, otherwise `reasoner-sdk`), version `0.2.0` to reflect the new sync endpoint.
2. `client.ts`: add `runSync()` against `/api/agent/run/sync` (one request, no SSE parsing) alongside `runToCompletion()`, and align `RunSummary` field names with the Python `RunSummary` from Workstream 0. Add a typed error for the new 504-with-`client_run_id` case.
3. CI: a `release-sdk` workflow gated on `npm test` (contract tests) plus the Python `tests/test_sdk_contract.py`, publishing with provenance on an `sdk-v*` tag.
4. `sdk/typescript/README.md`: add the MCP alternative and a "which surface should I use" table, so the SDK is not presented as the only integration path.
5. **Python client: deliberately not built.** The docs page ships a 25-line httpx snippet that does the whole job, and the sync endpoint makes even that optional. Revisit only if issues ask for it — a published package is a maintenance commitment, and `reasoner.headless` already covers in-process Python use.

**Files touched:** ~5 modified, 1 new workflow. ~150 added.
**Risk:** low.

---

## 7. Cross-cutting changes

### Settings (`core/settings.py`, `.env.example`)

| Setting | Default | Purpose |
| --- | --- | --- |
| `ENABLE_LEGACY_AGENT_API` | `false` | Keeps `require_api_key` handlers alive for self-hosters mid-migration |
| `ENABLE_MCP_HTTP` | `false` | Mounts the Streamable-HTTP MCP transport at `/mcp` |
| `MCP_MAX_CONCURRENT_RUNS` | `4` | Per-session ceiling; an agent loop can otherwise open runs faster than it reads them |
| `AGENT_SYNC_MAX_SECONDS` | `620` | Server-side ceiling for the blocking endpoint, just above the 600s pipeline cap |

### Observability

`REASONER_QUERIES_TOTAL` gains an `interface` label (`web` / `agent_http` / `agent_sync` / `mcp`), applied inside `RunObserver` — so "used by agents" becomes a number on a dashboard rather than an assertion. Add a panel under `docs/monitoring/`.

### Import-linter

Run `lint-imports` after each workstream. Per the project's gate note, invoke it from **PowerShell** — the rtk Bash wrapper suppresses lint stdout. No new exemptions are expected; if `api/mcp/` needs one, the review question is "why does an adapter need a private import?" before the exemption is granted.

### Documentation (lands in the same PRs, not after)

| Doc | Change | Trigger |
| --- | --- | --- |
| `ui-next/src/lib/docs.ts` → `agent-integration` | Rewrite "Read the stream" + "Self-hosted deployments"; add MCP section | WS1, WS3 |
| `ui-next/src/lib/docs.ts` → `api-reference` | Add `/api/agent/*` to the catalogue | WS1 |
| `ui-next/src/app/llms.txt/route.ts` | Add MCP + agent endpoints to "Key facts" | WS3 |
| `README.md` | Replace the self-hosted-only caveat added 2026-08-15 | WS1 |
| `docs/MCP.md` (new) | Install, config, tool reference | WS3 |
| `CLAUDE.md` §3 | Add `api/mcp/` to the structure map | WS3 |

---

## 8. Sequencing

```
WS0 (metering + summary extraction)      ← blocks everything, no user-visible change
     ├──▶ WS1 (hosted agent endpoints)   ← needs metered(); frontend proxy after backend
     │        └──▶ WS4 (SDK publish)     ← needs the sync endpoint to exist
     ├──▶ WS2 (tool schema)              ← independent apart from the router file
     └──▶ WS3 (MCP)                      ← needs metered() + summarise(); WS2 informs descriptions
```

| # | Workstream | PRs | Lines | Risk | Ship gate |
| --- | --- | --- | --- | --- | --- |
| 1 | WS0 foundation | 1 | ~180 | Low | `/api/run` integration tests green; ledger unchanged for a UI run |
| 2 | WS2 tool schema | 1 | ~200 | Low | `sdk/contract/tools.json` snapshot committed |
| 3 | WS1a backend | 1 | ~250 | Medium | Sync run debits the ledger exactly once; 409 on duplicate `client_run_id` |
| 4 | WS1b proxy + docs | 1 | ~170 | Medium | Bearer-only guard tested; docs drift test green |
| 5 | WS3 MCP | 2 | ~700 | Medium | Host connects, runs, and is billed; no admin tools listed |
| 6 | WS4 SDK | 1 | ~150 | Low | Published; contract tests green in CI |

Total ≈ 1,650 lines added, ~70 removed, across 7 PRs. WS0→WS2 is same-day work; WS3 is the multi-day item.

---

## 9. Definition of done

- [ ] A run through `/api/agent/run/sync` with an `rsn_live_` key appears in the ledger with the same `total_cost_usd` as the identical run through `/api/run`, charged once.
- [ ] `curl https://<host>/api/agent/run/sync -H "Authorization: Bearer rsn_live_…"` returns a populated `RunResult` from the public domain.
- [ ] `GET /api/agent/tools` appears in `/openapi.json`, is cacheable, and its Anthropic-format payload registers unmodified as a tool.
- [ ] An MCP host config pointing at `mcp_server.py` exposes `reasoner_run`; a run reports per-phase progress and settles credits.
- [ ] No admin, key-management, or GDPR endpoint is reachable through MCP.
- [ ] `lint-imports` passes; any layer-contract diff is justified in the PR body.
- [ ] Every documentation surface in §7 reflects shipped behaviour; the drift test enforces it.
- [ ] `ENABLE_LEGACY_AGENT_API=false` on a fresh install, with the removal version named in `.env.example`.

---

## 10. Rollback

Each workstream is one revert. WS0 is behaviour-preserving, so reverting WS1–WS3 leaves a system identical to today's except for a better-factored metering path. Two items are not cleanly reversible: the npm publish (mitigate — publish `0.2.0` only after WS1 is live; deprecate rather than unpublish) and any MCP host config users have already added (mitigate — keep tool names stable from first release; add tools, never rename them).

---

## 11. Alternatives considered and rejected

| Option | Why not |
| --- | --- |
| Leave `/api/agent/*` on the legacy `AuthManager` and just proxy it | Ships an unmetered path to a paid product from the public domain. That is the bug, not the shortcut. |
| Middleware-level CSRF bypass for all bearer requests | `require_csrf` already exempts *authenticated* API-key requests (`auth_deps.py:216`). Middleware doing it earlier would exempt on token shape, not validity — the exemption becomes the bypass. |
| Implement pipeline logic inside the MCP server for speed | Two implementations of routing and metering. The point of the hexagon is that this is not a tradeoff you are allowed to make. |
| Generate the tool schema from `/openapi.json` at runtime | Exposes every field and endpoint by default, including ones no agent should call. An explicit allowlist fails closed. |
| Publish a Python SDK alongside the TypeScript one | A 25-line httpx snippet plus `reasoner.headless` already cover it. Revisit on demand. |
| Skip WS0 and copy the settlement block into the new endpoints | That copy is where the next silent free-run bug comes from. |
