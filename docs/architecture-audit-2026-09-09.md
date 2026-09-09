# Architecture Audit — Reasoner

Date: 2026-09-09. Tree: branch `studio-adopt` at `25cc8bd`.
Supersedes `docs/architecture-audit-2026-06-02.md` for the current tree.
Protocol: EGFV. Every non-trivial claim carries `[VERIFIED]`, `[HYPOTHESIS]`,
`[UNKNOWN]` or `[FALSE]`. `[VERIFIED]` means the cited line was read on this
tree, not that a document asserts it.

Scope: the Python backend, `src/reasoner/`. `ui-next/` is excluded — it is
governed by a separate studio pipeline and was not evaluated.

---

## Step 0 — Input gate

| Input | Status |
|---|---|
| Full codebase + tree | Present |
| Primary entry points | Present, identified below |
| ADRs | Present — `docs/adr/001..005` (hexagonal, event-sourcing/CQRS, HyperGate, cross-lab routing, neuro tiering) |
| README / design docs | Present — `README.md` (28 KB), `CLAUDE.md`, `ARCHITECTURE_MINDMAP.md`, `docs/CODEMAPS/` |
| Dependency manifests | Present — `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `requirements.lock.txt` |
| Deployment manifests | Partial — `Dockerfile`, `docker-compose.yml`, `docker-compose.observability.yml`. **No k8s/helm manifests exist** |
| CI/CD configs | Present — 9 workflows under `.github/workflows/`, plus `scripts/ci-local.sh` and `.githooks/` |

No required input is missing. Horizontal-scaling findings below are therefore
assessed against docker-compose topology, not an orchestrator manifest —
`[UNKNOWN — no k8s manifest provided]` is appended where replica count matters.

---

## Phase 1 — Architectural fingerprinting

### DETECTED ARCHITECTURE: top-down N-tier layering over a global-singleton substrate, with hexagonal scaffolding that is mostly unused on the hot paths.

Evidence, from code rather than docs:

1. `[VERIFIED]` `application/orchestrator.py:30` and `application/pipeline.py:47-48`
   import the **concrete** `ProviderRouter` and `LLMExecutor` at module level, not
   a port.
2. `[VERIFIED]` Port adoption is measurable and low: `core/ports/llm_port.py`'s
   `LLMPort` has **2** importers (`application/flows/base.py:9`,
   `application/flows/prism_research.py:15`) against **26** import sites of the
   concrete `ProviderRouter` repo-wide.
3. `[VERIFIED]` `core/settings.py:542` — `settings = Settings()`, a module-level
   singleton whose class attributes are evaluated at first import (`:62-130`).
   **100** direct import sites across `src/`. This is config-as-service-locator,
   the inverse of injection.
4. `[VERIFIED]` Dependency injection is implemented as module-global setters
   mutated at startup, not constructor injection: `core/search.py:22`
   (`set_build_provider`), `core/ports/model_registry_port.py:83`,
   `memory_port.py:61`, `shared_cache_port.py:52`.
5. `[VERIFIED]` `core/search.py:37-40` reaches infrastructure through
   `importlib.import_module("reasoner.infrastructure.search.discovery")` — a
   string literal, invisible to both grimp and the AST fitness test.

**Where the code contradicts the doc.**

`[VERIFIED]` `CLAUDE.md:19` states "Application depends on Domain/Core only".
There are **59** `application → infrastructure` imports (19 module-level, 40
function-local).

`[VERIFIED]` `.importlinter:14-27` encodes the *opposite* rule. Its `layers`
list places `reasoner.application` **above** `reasoner.infrastructure`; under
import-linter's layers semantics a higher layer may import a lower one, so the
config sanctions `application → infrastructure` as legal. **The config is
N-tier; the prose claims hexagonal. These are not two views of one design; they
are two different designs.**

`[VERIFIED]` `tests/architecture/test_layer_boundaries.py` maintains a *third*
ledger: `FORBIDDEN_IMPORTS` at `:54-70` forbids `application → api` and
`core → application`, but **not** `application → infrastructure`. Three
enforcement artifacts, three different architectures, none matching the other
two.

**What does hold.** `[VERIFIED]` Domain purity is real: zero
`domain → infrastructure` and zero `domain → api` imports across 24 files, and
no pydantic/fastapi/sqlalchemy/httpx/starlette import anywhere in `domain/`. The
only outward edges from domain are three lazy imports into `application`, all in
`domain/pipeline_state.py:710,715,721`, all documented and all listed in
`.importlinter:102`.

### Entry points and bootstrap divergence

| Entry | File | Wires |
|---|---|---|
| ASGI/HTTP | `asgi.py:6` → `api/__init__.py:88-224` (lifespan) | `init_default_subscribers`, `setup_event_bus_integration`, `set_build_provider` (`:206`), `set_model_registry_port` (`:207`), `inject_shared_cache_port` (`:209`), `set_memory_port` (`:220`) |
| CLI | `main.py` → `src/reasoner/main.py` | `set_model_registry_port` (`:227`), `set_memory_port` (`:234`), `init_default_subscribers` (`:304`). **No `set_build_provider`** |
| Headless | `src/reasoner/headless.py` | `set_model_registry_port` (`:137`), `set_memory_port` (`:145`). **No `set_build_provider`** |
| MCP stdio | `mcp_server.py:24` | **No port setters at all.** Reads `REASONER_API_KEY` straight from env at `api/mcp/context.py:36` |
| Launcher | `start_all.py` | No DI; spawns uvicorn + `npm run dev` as subprocesses |

`[VERIFIED]` The three non-ASGI entries reach `core.search` code paths with
`_BUILD_PROVIDER is None`. See Phase 5 — that seam turns out to be inert on
*every* path, so the divergence is currently harmless and structurally wrong.

### Data flow topology

`[VERIFIED]` Async throughout, push-based over SSE. A run is an
`asyncio.create_task` created *inside* the SSE generator
(`api/streaming.py:160`), not a queued job: `fastapi.BackgroundTasks` appears
nowhere in `src/reasoner` (0 grep matches). Run lifetime is bound to the HTTP
connection; disconnect is polled every 10 chunks and cancels the task
(`streaming.py:164-193`), and the comment at `:190-192` states this is "the only
thing that cancels a run whose client is gone."

### Configuration and secrets

`[VERIFIED]` `core/settings.py:4-5` claims it is "the ONLY module in the project
that reads from the process environment." That claim is `[FALSE]`. **26
secret-shaped env reads exist elsewhere**, including
`infrastructure/billing/stripe_adapter.py:21` (`STRIPE_SECRET_KEY`),
`infrastructure/billing/webhooks.py:157` (`STRIPE_WEBHOOK_SECRET`),
`security/encryption.py:159,206`, `infrastructure/llm/registry.py:586,596`, and
`domain/preset_core.py:343` — **an environment read inside the domain layer**.

`[VERIFIED]` Concrete divergence risk: `settings.py:70` resolves
`OPENROUTER_API_KEY` frozen at import time, while
`infrastructure/llm/registry.py:586,596` read live `os.environ`. Two sources for
one value, with different lifetimes.

---

## Phase 2 — Compliance matrix

| Module | Detected pattern | Intended pattern | Drift | Violations | Severity | Evidence |
|---|---|---|---|---|---|---|
| `domain/` | Mostly-pure entities + a rich watermark subdomain | Dependency-free domain | **Low** | Import-time file I/O; env read; vendor identity in domain data | MEDIUM | `domain/pricing.py:43-47,86,95`; `domain/preset_core.py:343`; `domain/preset_registry.py` names OpenRouter ids |
| `core/` | Ports + settings singleton + constants | Ports only, no outward edges | **Medium** | `core/search.py:37-40` string-literal infra import; `core/degrade.py:75` lazy infra import; `core/` imports `domain/` 9× at module level | MEDIUM | cited inline |
| `application/` | N-tier service layer over concrete infra | "Domain/Core only" | **High** | 59 `application → infrastructure` imports; `handlers.py:318-319` reaches `api._run_store`, a **private** attribute of the outermost layer | HIGH | `.importlinter:29,35-40,65`; `handlers.py:318` |
| `application/flows` | Strategy + runner composition | Same | **Critical** | The canonical `WorkflowRunner` is **feature-flagged off by default** and enabling it raises `TypeError` on the first phase | CRITICAL | `core/settings.py:121-122`; `application/pipeline.py:501-513` |
| `api/execution/pipeline.py` | Second, divergent phase engine | Should reuse `WorkflowRunner` | **Critical** | 690-line god-method; **lines 481–520 are unreachable on every path** | CRITICAL | verified in Phase 4 |
| `infrastructure/llm` | Router + executor + registry | Adapters behind ports | **Medium** | `executor.py` enforces **spend caps** — a billing concern inside an LLM adapter; router terminal failure returns an empty-string success shape | HIGH | `executor.py:720,759`; `router.py:585-588` |
| `infrastructure/persistence` | Two engines side by side | One event store | **High** | SQLite and Postgres both live; `usage_quotas`, `api_keys`, `events` each have multiple unrelated writers | HIGH | Phase 5 |
| `infrastructure/llm/spend_tracker.py` | In-process dict | Durable counter | **High** | Monthly billing ceiling is a process-local dict; effective ceiling is `monthly_usd × worker_count` | HIGH | `spend_tracker.py:7-13,23` |
| `hypergate/` | 5 parallel sub-agents + tiebreaker | Same | **Low** | 2 module-level + 1 lazy infra import, all tagged "needs DI to remove" | LOW | `.importlinter:82-89` |
| `neuro/` | Tiered memory with tenant isolation | Same | **Low** | Not in `.importlinter` `layers` at all, so ungoverned; `neuro/server.py:587` imports `api.dependencies` | MEDIUM | `.importlinter:14-27`; `neuro/server.py:587` |
| `security/persuasion_defense.py` | Full plugin architecture | — | **Total** | 1092 lines, zero production call sites | MEDIUM | Phase 5 |
| `api/dependencies.py` | Entitlement gate | Enforced tier check | **Total** | `check_preset_access` has zero production callers and its body says it is "deliberately not enforced" | HIGH | `api/dependencies.py:708-725` |

---

## Phase 3 — Dependency and coupling analysis

### Circular dependencies

All four below are `[VERIFIED]` and all four are broken by function-local
imports — the lazy import *is* the cycle-breaker, which is what makes the cycle
invisible to a module-level scan.

1. **`domain.pipeline_state` ↔ `application.services.pipeline_service`.**
   `pipeline_service.py:8` imports `PipelineState` at module level;
   `pipeline_state.py:710,715,721` import back, all function-local, comment at
   `:709` reads "COMPAT: Delegated to PipelineService."
2. **`application` ↔ `infrastructure.llm.executor`.** `application/pipeline.py:47`
   imports the executor at module level; `executor.py:49` imports
   `application.event_bus.bus` inside `_get_event_bus()`, with the comment "Lazy
   import to avoid circular dependency with api/__init__.py."
3. **`application.event_bus` ↔ `infrastructure.websocket.manager`.** `bus.py:28`
   imports `infrastructure.observability.langfuse_subscriber` at module level;
   `manager.py:562,393` import back, function-local.
4. **`reasoner.models` ↔ `application.services.pipeline_service`**, same shape.

`[VERIFIED]` For `application/`, lazy infra imports (40) outnumber module-level
ones (19) more than 2:1. **The lazy channel is where most boundary crossing
lives.** That is the hidden coupling in this codebase: not undeclared, but
declared in a place static layering does not look.

### Layer leaks

`[VERIFIED]` `application/handlers/handlers.py:318-319` — `import reasoner.api as api`
then `await api._run_store.request_cancel(...)`. Application reaching the
outermost layer, at a **private** attribute. Listed at `.importlinter:65` and
`test_layer_boundaries.py:46`, which calls itself "a debt ledger, not a blanket
exemption" — but nothing bounds its growth.

`[VERIFIED]` `.importlinter` carries **59 `ignore_imports` exceptions against 1
contract**, with `unmatched_ignore_imports_alerting = warn` (`:13`), so stale
exceptions never fail the build.

Confirmed stale or redundant entries:

- `[VERIFIED]` `.importlinter:66` — `application.services.data_eraser → reasoner.api.cache`.
  `data_eraser.py` contains **zero** `reasoner.api` imports. Dead entry.
- `[VERIFIED]` `.importlinter:90` and `:100` target imports inside
  `if TYPE_CHECKING:` blocks while `:3` sets `exclude_type_checking_imports = True`.
  Both redundant.
- `[VERIFIED]` `infrastructure.renderer → application.services.renderers` is
  listed twice (`:29` and `:56`).

`[VERIFIED]` Five packages are absent from the `layers` list entirely and are
therefore ungoverned by the contract: `phases`, `neuro`, `healing`, `documents`,
`utils`.

### Shared mutable state

`[VERIFIED]` All process-local, all diverge across uvicorn workers:
`spend_tracker._SPEND` (`:23`), `api/cache.py:27` `_MEMORY_CACHE`,
`router.py:224-226` `_GLOBAL_RESOLVED_CACHE` / `_PER_MODEL_SEMAPHORES`,
`rate_limiter.py:113` `_buckets`, `api/dependencies.py:73`
`_provisioned_user_ids`, `neuro/server.py:140-214` `TenantManager._tenants`
(L1/L2 caches — the docstring at `:289-297` says a second instance "would hold a
divergent copy"), `application/services/adaptive_routing.py:406`
`_SHARED_REGISTRY`, and `domain/models.py:44` `PerspectiveRegistry._known`,
which is class-level mutable state **in the domain layer**.

`[VERIFIED not a finding]` `infrastructure/llm/registry.py:563` freezes
`_REGISTRY` behind `MappingProxyType` after import, deliberately, so that
post-init mutation is a `TypeError` rather than a silent data race.

### Tight coupling hotspots

`[VERIFIED]` `core/settings.py` — 100 importers, the highest afferent coupling in
the tree, and its values are frozen at first import. `:28-40` says so
explicitly: any fixture running after collection is "already too late to isolate
anything."

`[VERIFIED]` `api/execution/pipeline.py:48` — the single chokepoint through which
every HTTP, SSE, CLI, headless and MCP run passes.
`grep -rn "ReasonerPipeline(" src/reasoner` returns exactly one hit,
`application/services/pipeline_service.py:33`.

---

## Phase 4 — AI orchestrator deep review

### Two live phase engines, and the canonical one has never run

`[VERIFIED]` `core/settings.py:121-122` — `WORKFLOW_RUNNER_ENABLED` defaults to
`"false"`. `application/pipeline.py:492-513` states, in the source:

> Retries, per-phase timeouts, the quality gate, PHASE_* events,
> `_current_phase_key` and therefore phase_tokens/phase_durations have never
> executed on any CLI or headless run.

and:

> None of those members exist yet, so the first phase raises TypeError with this
> on.

`[VERIFIED]` So `WorkflowRunner` — the layer that owns retry budgets, per-phase
timeouts and the quality gate — is off by default on CLI and headless, and
turning it on raises `TypeError` on the first phase.
`application/flows/services.py:96-101` takes the bare fallback
`await step.fn(state, self); return True` instead.

### C-A. The SSE path's quality gate is unreachable code

**`[VERIFIED]` — the most severe finding in this audit, verified structurally
rather than by eye.**

`api/execution/pipeline.py`, the retry loop at line 385, parsed:

```
for  (col 16, line 385)
  body[0]  = Try, lines 386-478
             try-body   ends: Break @396
             except TimeoutError @397 ends: Break @428
             except Exception  @429 ends: Break @478
  body[1..11] = lines 481-520   <-- siblings of the Try, col 20
```

All three paths through the `try` statement end in `break`. Statements 2 through
12 of the loop body therefore **never execute on any input**. What is in them
(lines 479–520, read verbatim):

- `await phase_monitor.evaluate(name, state, attempt=...)` — the quality gate
- the `phase_quality` SSE emit and its `_tracked_broadcast`
- `state.quality_history.append({...})`
- `if quality_result.passed or retry_attempt >= max_retries: break`
- `state.quality_hints[name] = " ".join(quality_result.suggestions)`
- the `phase_retry` SSE emit
- `reset_phase_state(name, state)`

Consequences, all `[VERIFIED]` by construction:

- On the production SSE path the retry budget is consumed **only** by exceptions,
  never by low output quality.
- `state.quality_history` is never populated there.
- No client has ever received a `phase_quality` or `phase_retry` SSE event from
  this path.

Combined with the previous finding: `WorkflowRunner`'s quality gate is off and
broken, and the SSE path's quality gate is dead code. **The quality gate does not
run anywhere in this system today.**

The `# Phase executed successfully — run quality check` comment at `:479` shows
the block was written to live inside the `try`. It sits one statement too late.

### Orchestration model

`[VERIFIED]` Centralized, three tiers: `PipelineOrchestrator` (preflight →
execute → postflight, `orchestrator.py:113-140`), `ReasonerPipeline` per run
(`application/pipeline.py:80-136`), and a *third* de-facto coordinator at
`api/execution/pipeline.py:293-560` that re-instantiates `WorkflowFactory`,
flattens `strategy.get_phases()` and runs its own retry/timeout loop. The
duplication is acknowledged in-code at `application/flows/runner.py:57-62`.

`[VERIFIED]` Binding is a strategy registry, not mixins:
`application/flows/factory.py:36-62` is a hardcoded 24-entry dict.
**Unknown methods silently resolve to `MultiPerspectiveFlow`** (`factory.py:67`),
so a typo'd method name produces a plausible run rather than an error.

### Routing separation

`[VERIFIED]` Mostly clean: flows call `services.call_llm(role=...)` with role
strings, never model ids (`application/flows/services.py:72-94`).

`[VERIFIED]` Leaks: `application/services/gate_service.py:72-118` hardcodes
`_HYPERGATE_PRIMARY = "ministral-14b"` and its role/fallback tables;
`application/flows/writing_phases.py:66` and `article_phases.py:99` sniff
`"sonar" in model_used.lower() or "perplexity" in ...`;
`application/flows/perspective_phases.py:103-124` hardcodes vendor-bloc sets.

### Async and concurrency

`[VERIFIED]` No `requests` anywhere; HTTP is `httpx`. No sync `time.sleep` or
`subprocess.run` on any async path — both are confined to `start_all.py` and
`healing/run_healing.py`, both sync functions.

`[VERIFIED]` Blocking file I/O **inside `async def`**, four sites:
`application/services/deadletter_replay_service.py:51,106,167` (`read_text`;
notably the *write* path at `:172-188` correctly uses `asyncio.to_thread`) and
`infrastructure/execution/subprocess_executor.py:89-96` (`write_text` inside
`async def execute`).

`[VERIFIED]` Backpressure exists and is real: per-model `asyncio.Semaphore`
(`router.py:225,265-275`, default `LLM_CONCURRENCY_LIMIT` 30), event bus
`Queue(maxsize=1000)` + `Semaphore(200)` (`bus.py:72,79,136`), SSE queue
`maxsize=256` (`streaming.py:178-186`), absolute wall-clock run cap
(`streaming.py:145-160`). Non-critical bus events are dropped with a dead-letter
write when the queue is full (`bus.py:216-231`); critical events `await put()`.

`[VERIFIED]` Concurrent LLM calls are **partially** bounded. Four fan-outs carry
a local `Semaphore(4)` (`cognitive_phases.py:93`, `coding_phases.py:160`,
`search_phases.py:482`, `core/rerank.py:333`). The rest — perspectives
(`perspective_phases.py:188`), jury (`jury_phases.py:106,155`), Delphi
(`delphi_phases.py:26,110`), debate (`debate_phases.py:42,87,132`), all five
subagent hyper-agents, and HyperGate's 5 sub-agents (`hyperagent.py:257`) — are
bounded only by the per-model semaphore, which is **per process**.
`[HYPOTHESIS]` With N uvicorn workers real provider concurrency is `limit × N`
`[UNKNOWN — no k8s manifest provided]`.

`[VERIFIED]` `application/flows/augmentation.py:277` is the only `gather` over
LLM calls without `return_exceptions=True`; a per-task try/except at `:270-272`
covers it.

`[VERIFIED]` No `asyncio.TaskGroup` anywhere in `src/reasoner`.

### State and context

`[VERIFIED]` `PipelineState` is threaded explicitly through every phase signature
`(state, services)` and mutated in place — deliberately, and documented:
`perspective_phases.py:180-185` carries `PhaseOutput(..., mutated_in_place=True)`
with the note that "every executor … calls the phase function and drops its
return."

`[VERIFIED]` No `contextvars` in the orchestration path.

`[VERIFIED]` One ambient coupling: `state._current_phase_key`, a private
attribute set by both runners (`flows/runner.py:70`,
`api/execution/pipeline.py:364`) and read by the infra executor for token and
cost attribution (`executor.py:520-523,834-847`). It is not in the declared field
set, so nothing type-checks it and nothing prevents a phase running with a stale
key.

`[VERIFIED]` Tenant isolation in neuro is enforced at a single chokepoint,
`neuro/server.py:264-286` `tenant_key()`, deriving owner from
`Depends(get_optional_user)` rather than the request body, and applied at all
three entry points (`:382,461,493`). Its docstring records the prior
vulnerability it closed: `agent_id` alone once selected the memory directory, so
anyone knowing another user's conversation id could recall or poison it.
Recall-side hardening is real — chunks are re-run through
`neutralize_for_replay` and `schema_version < 1` chunks are dropped as
unattributable (`orchestrator.py:385-463`), and only the run's own synthesis is
eligible for `learn`, because the `previous_synthesis` fallback was a
caller-controlled write primitive into memory (`orchestrator.py:518-529`).
**This is the best-defended subsystem in the codebase.**

`[VERIFIED]` One gap: `require_neuro_key` (`neuro/server.py:245-261`) allows
**all traffic through when the key is unset**.

### Failure semantics

`[VERIFIED]` **Four independent retry layers with four different policies**, and
the declared constant is used by none of them:

| Layer | Policy | Cite |
|---|---|---|
| Provider | `max_retries=2` | `infrastructure/llm/base.py:114-116` |
| Router | fallback chain, `single_attempt=True` to avoid compounding | `router.py:568`, comment `:117-129` |
| Phase | `get_phase_retry_budget()`, default 1, **fixed 1s sleep, no backoff, no jitter** | `constants_limits.py:246-261`; `flows/runner.py:161` |
| Executor | one-shot doubling on `finish_reason == "length"` | `executor.py:577-635` |
| Event bus | 3 retries, exponential + jitter | `bus.py:247-267` |

`[VERIFIED]` `DEFAULT_MAX_RETRIES = 3` (`constants_limits.py:48`) is declared and
matches none of the above.

`[VERIFIED]` `base.py:248` — `if isinstance(exc, ProviderError) or not is_retryable(exc): raise`
short-circuits **before** `.retryable` is consulted, so `RateLimitError.retryable = True`
never fires at that layer. The in-code comment says changing it is deferred.

`[VERIFIED]` **Terminal failure returns a success-shaped value.** When the whole
fallback chain is exhausted the router does not raise; it returns
`(DegradedLLMResponse(text="", error=...), {})` — an empty-string body with an
empty metadata dict (`router.py:585-588,598-601,621-624,634-637`).
`[HYPOTHESIS]` Downstream, every phase feeds `raw` to `extract_json(raw)`, so a
fully exhausted provider chain surfaces as a JSON parse failure rather than a
provider failure. This is the same "signal and proceed on the value you just
admitted was wrong" shape the P5 audit named in
`docs/plans/audit-remediation-2026-09-08.md`.

`[VERIFIED]` `is_run_fatal` covers only `ProviderCreditsExhaustedError` and
`AuthenticationError` (`core/exceptions.py:290-304`). Everything else either
retries or leaves the phase's output missing and continues
(`flows/runner.py:138-158`).

### Tool execution

`[VERIFIED]` Well isolated. `ContainerExecutionSandbox` is an httpx client to a
separate `sandbox-worker` container holding the Docker socket; the API process
never touches Docker (`container_sandbox.py:1-9,50-134`). Selection is
fail-closed — `NoopExecutor`, never `None`, on disable or construction failure
(`flows/services.py:25-67`) — and `settings.py:551-560` raises at import if
production combines `enabled=true` with a non-container mode or a missing
`SANDBOX_WORKER_TOKEN`. A 30s-TTL health check gates every call and returns
`blocked_reason="sandbox_unhealthy"` without dispatching.

`[VERIFIED]` Prompt-injection containment is present: stdout and stderr are
wrapped by `_wrap_external_content(...)` before entering the interpret prompt
(`phases/pot.py:57-64`).

`[VERIFIED]` One contract break: `container_sandbox.py:122-134` does
`response.json()` then indexes 9 required keys directly, with no schema check. A
malformed worker response raises `KeyError`, contradicting the port contract at
`core/ports/code_executor.py:80-82`: "The executor MUST NOT raise on execution
failure."

### Scalability

**The single point most likely to fail under 10× load: `api/execution/pipeline.py`
as a request-coupled executor.** `[VERIFIED]` A run is an in-request
`asyncio.create_task` whose lifetime is the HTTP connection; there is no queue,
no worker tier, and no way to resume a run whose connection dropped. 10× arrival
rate means 10× concurrent event-loop-resident pipelines in one process, each
holding an SSE queue, full state, and per-model semaphore slots.

`[VERIFIED]` The orchestrator *objects* are per-request, but the process is not
stateless. Docker Compose runs a single `backend` service and
`docker-entrypoint.sh` takes an env-driven worker count, so worker count > 1 is a
supported configuration — at which point every per-process structure listed in
Phase 3 diverges. `[UNKNOWN — no k8s manifest provided]` for multi-node.

`[VERIFIED]` Redis/Valkey is used correctly as coordination, not source of truth:
run state with 300s TTL (`redis/run_state.py:27-40`), circuit-breaker Lua, Stripe
webhook idempotency, WS tickets, HyperGate decision cache, and read-through
caches over Postgres repos. `run_state.py:104-105` **disables the in-memory
fallback in production** and raises rather than degrading — the right call.

`[VERIFIED]` One exception: `ValkeyStateAdapter` swallows every exception and
returns `False`/`None`/`[]` (`valkey/state_adapter.py:41-73`), so a Valkey outage
silently degrades `set_nx` idempotency to "not set". These are among the sites
the newly-fixed silent-failure ratchet now counts (commit `25cc8bd`).

`[VERIFIED]` Container boundaries do reflect service boundaries: 7 services —
`caddy`, `backend`, `frontend`, `postgres`, `valkey`, `sandbox-worker`,
`docker-socket-proxy` — with the sandbox's Docker access mediated by the proxy
rather than a bind-mounted socket.

`[VERIFIED]` **Runtime/type-checker version drift**: `Dockerfile:2` and
`.github/workflows/test.yml`'s `PYTHON_VERSION` both pin **3.14**, while
`pyproject.toml:9` declares `requires-python = ">=3.12"` and `:30` sets
`python_version = "3.12"` for mypy. The type checker models a different Python
than the one that runs in CI and in production.

---

## Phase 5 — Anti-pattern detection

**God module / god method.** `[VERIFIED]`
`api/execution/pipeline.py` — `PipelineExecutionService.execute_run` is a
**single method spanning lines 48–739 (~690 lines)**, the clearest god-method in
the repo and the one containing the dead block above.
`application/services/serializers.py` (1159 lines) holds wire format plus every
phase's schema, with three ~225-line single functions.
`api/__init__.py` (1110) is app factory + lifespan + composition root + six
endpoint handlers.
`infrastructure/llm/executor.py` (905) — `execute()` alone spans 102–576, its own
docstring enumerates six responsibilities, and it also enforces **spend caps**, a
billing concern, inside an LLM adapter.
`[VERIFIED not a finding]` `domain/preset_registry.py` (1151) and
`infrastructure/llm/registry.py` (874) are data literals, not logic sprawl;
`application/pipeline.py`'s bulk (lines 220–366) is ~40 two-line back-compat
delegators, documented as such at `:221-224`.

**Orchestrator bottleneck.** `[VERIFIED]` Confirmed — see Phase 3.

**Anemic domain model.** `[VERIFIED]` Split, not uniform. Anemic:
`domain/saas.py` (5 dataclasses, zero methods), `task_requirements.py`,
`telemetry.py`, and `pipeline_state.py` where ~48 of ~70 methods are
property/setter pairs delegating to `method_state.get/set` (`:429-608`), with
serialization living in `application/services/pipeline_service.py:281` (466
lines). Rich: the whole `domain/watermark/` subtree (`layer_a.py`, `rules.py`'s
8 strategy classes, `marks.py`), `domain/spend_limits.py:35 tightest()`, and
`domain/preset_core.py:286 __post_init__`, which validates routing keys against
`_KNOWN_ROUTING_ROLES` and raises.

**Temporal coupling.** `[VERIFIED]` Five module-level DI slots that must be set
before first use. `get_model_registry_port` **raises** if unset (fails loud);
`memory_port` and `shared_cache_port` return `None` (fail silent). The dangerous
one is `domain/preset_core.py:311-341`:

```python
try:
    registry = get_model_registry_port()
except RuntimeError:
    return []
```

If a `PipelinePreset` is constructed before injection, `required_env_vars` stays
empty, so `check_keys()` / `missing_keys()` report nothing missing **for every
preset** — the API-key preflight becomes a no-op with no error. The docstring
records that this exact bug already shipped once.
`domain/spend_limits.py:75-82` documents the sibling hazard: without injection,
cost estimates inflate **~4.4×** (`debate-budget` reads `$0.273` instead of
`$0.0615`), "which makes it look like no preset can ever pass at any cap."

**Premature abstraction.** `[VERIFIED]` Four ports have **zero** references
outside their own file: `core/ports/circuit_breaker_port.py` (two Protocols,
despite a docstring claiming "Implemented by infrastructure.circuit_breaker"),
`telemetry_port.py` (duplicated by `application/ports/service_protocols.py:85`,
which is what actually gets used), `crypto_port.py`, and
`capability_registry_port.py` — whose three consumers type the parameter `Any`
and name the port only in a comment (`adaptive_routing.py:70`,
`benchmarks/engine.py:50`, `learning/online_learner.py:44`). Eight more ports
have exactly one implementation; `crypto_port.py:8-11` says so about itself:
"no second implementation to justify it." `PixelScrubberPort`'s only
implementation is a Null Object that always reports unavailable.
`[VERIFIED not a finding]` Ports with genuine multiplicity: `ApiKeyRepository`,
`CreditRepository`, `SharedCachePort`, `DistributedStatePort`,
`SearchServicePort`, `CodeExecutorPort`, `RoutingConstraintPort`, `Clock`.

**Infrastructure leakage into domain.** `[VERIFIED]` Three: import-time
filesystem I/O (`domain/pricing.py:43-47`, with module-level side effects at
`:86` and `:95`), an env read (`preset_core.py:343`), and vendor identity baked
into domain data (`preset_registry.py`, `pricing.py:112`). Counter-evidence that
the boundary is otherwise held: `preset_core.py:319-321` explicitly routes
through `ModelRegistryPort` "rather than importing infrastructure.llm.registry:
domain must not depend on infrastructure."

**Shared database coupling.** `[VERIFIED]` Two engines run simultaneously. Only
the *event store* is switchable (`event_store.py:846-856`); `error_store`,
`feedback_store`, `telemetry_store`, `auth_store` and `pipeline_ownership_repo`
are hard-bound to SQLite, so a Postgres deployment still runs 5+ SQLite files
beside it. `pipeline_ownership_repo.py:156-157` documents the seam. Three tables
have multiple unrelated writers:

- `usage_quotas` — `quota_repo_postgres.py:60,117,127` (per-request consumption)
  and `subscription_repo.py:140,150-157` (Stripe webhook / tier change), both
  taking `FOR UPDATE` locks on the same row from different call graphs.
- `api_keys` — two different schemas on two different engines
  (`auth_store.py:27`, SQLite, PK `key_hash`; `api_key_repo_postgres.py:80`).
- `events` / `aggregates` / `snapshots` — independently defined by both stores
  and **not schema-equivalent**: Postgres adds partitions and a `read_models`
  table that SQLite lacks.

**Dead code.** `[VERIFIED]` Four confirmed:

1. `api/dependencies.py:708 check_preset_access` — grep across `src/` returns only
   the definition. Body: a `logger.debug` and an unconditional 403 in production,
   with the comment "deliberately not enforced."
2. `application/services/feedback_router.py` — whole module, zero callers in
   `src/`, `tests/` or `scripts/`, while three docs and two skill maps describe it
   as shipped.
3. `security/persuasion_defense.py` — 1092 lines, referenced only by a 2-line
   shim and its own test. Its docstring names an insertion point
   (`ClaimExtractionStage` / `TwoTierVerificationStage`) whose classes **do not
   exist anywhere in `src/`**.
4. `core/search.py:20-29` — `set_build_provider` is called at
   `api/__init__.py:206`, but `_get_build_provider()` has **zero callers**;
   `infrastructure/search/discovery.py:36` defines its own independent version.
   The entire DI seam is inert. Corroborated verbatim by
   `tests/test_decompose_json_guard.py:23-27`.

**Over-engineering.** `[VERIFIED]` `security/persuasion_defense.py`: 4 Protocols,
1 ABC, 5 stage subclasses, a pipeline and an integration adapter — a complete
plugin architecture for a feature that is not installed.

**Under-engineering.** `[VERIFIED]` `infrastructure/llm/spend_tracker.py`: the
monthly billing ceiling for a paid SaaS is a plain in-process dict guarded by a
`threading.Lock`. Its own docstring states the effective ceiling is
`monthly_usd × worker_count` and that totals reset on restart, and names the fix
it did not make. The contrast is the finding: this repo already ships a
`SharedCachePort` and a `DistributedStatePort` with working Valkey adapters, and
this module uses neither. It is marked a deliberate MVP tradeoff, so it is
**acknowledged debt, not a hidden defect** — but it is debt on a revenue path.

---

## Phase 6 — Executive summary

### ARCHITECTURE SCORE: 5 / 10

The rubric's anchors at 4 and 6 each describe half of this codebase, so 5 is
where it lands, and the reason is worth stating rather than rounding away.

Against **6** ("moderate drift, 1–2 high-severity violations"): drift is more than
moderate and high-severity violations number more than two. Against **4**
("significant structural violations, hidden coupling, weak boundaries"):
boundaries are *not* weak where it matters most. Domain purity is genuinely
enforced with zero infrastructure imports across 24 files; tenant isolation is
single-chokepoint and hardened against a real prior vulnerability; the sandbox is
fail-closed with an import-time production guard; and the repo carries three
exact-equality ratchets, architecture fitness tests, 5 ADRs and 4264 passing
tests. Hidden coupling *is* present and is precisely locatable: 40
function-local infrastructure imports in `application/`, twice the module-level
count.

What holds the score down is not sloppiness. It is that **three separate
artifacts encode three different architectures** — `CLAUDE.md:19` says
hexagonal, `.importlinter:14-27` says N-tier, `test_layer_boundaries.py:54-70`
says a third thing — and **two of the system's own safety mechanisms are not
running**: the quality gate (dead on the SSE path, flagged-off and broken on the
runner path) and the entitlement gate (`check_preset_access`, zero callers).
Architecture that is documented but not enforced is a hypothesis, and here the
enforcement artifacts disagree with one another.

### MATURITY LEVEL: Early Production

Full billing (Stripe + PayPal), auth with scoped permissions, CSRF, rate
limiting, circuit breakers, a Docker Compose topology with a mediated sandbox, 9
CI workflows, event sourcing with snapshots. Against that: the monthly spend
ceiling is a per-worker dict, `check_preset_access` is inert, both git hooks are
opt-in and disabled by default (`.githooks/pre-commit:18`,
`.githooks/pre-push:19`), and `[UNKNOWN]` whether hosted CI currently executes —
`.githooks/pre-push:2-5` states GitHub Actions billing had lapsed, which was not
re-verified on this tree.

### PRIMARY RISKS, ranked by impact

1. **The quality gate does not run anywhere.** Dead code on the production SSE
   path (`api/execution/pipeline.py:481-520`); off-by-default and `TypeError` on
   the runner path. Every "quality-gated retry" claim in the documentation is
   currently false.
2. **Exhausted provider chains return success-shaped empties.**
   `router.py:585-588` returns `DegradedLLMResponse(text="")` rather than
   raising, so a total provider outage reaches the user as malformed JSON from a
   phase, not as an outage.
3. **Billing enforcement is per-worker.** `spend_tracker._SPEND` makes the real
   monthly ceiling `monthly_usd × worker_count`, and `check_preset_access`
   enforces nothing at all.
4. **Runs are coupled to HTTP connections.** No queue, no worker tier, no resume;
   connection loss is run loss, and it is also the only cancellation mechanism.
5. **Three disagreeing architecture ledgers plus 59 unratcheted `.importlinter`
   exceptions** with `alerting = warn`, at least four of which are already stale
   or redundant. The boundary rules cannot be trusted as written.

### CRITICAL VIOLATIONS (Phase 2, CRITICAL severity only)

- `api/execution/pipeline.py:481-520` — unreachable quality gate on the
  production path. `[VERIFIED]` by parsing: the preceding `try` and both handlers
  all terminate in `break`.
- `application/flows` — the canonical `WorkflowRunner` is feature-flagged off
  (`settings.py:121-122`) and raises `TypeError` on the first phase when enabled
  (`application/pipeline.py:509-513`). Retries, per-phase timeouts and PHASE_*
  events have never executed on CLI or headless runs.

### REFACTOR URGENCY: Immediate

Two safety mechanisms the documentation describes as active are not running, and
one of them is dead code rather than a disabled feature. Neither is expensive to
fix — the first is a dedent — but until both are addressed, any claim about
phase quality or preset entitlement in this system is unfounded. Everything else
on this list can wait for a normal sprint cadence.

---

## Phase 7 — Refactoring roadmap

### IMMEDIATE (fix before the next feature)

- **[Phase 4, C-A]** `api/execution/pipeline.py:479-520` → move the quality-gate
  block inside the `try`, replacing the bare `break` at `:396`. → The gate
  actually runs on the production path; `phase_quality` and `phase_retry` SSE
  events reach clients; `quality_history` populates. **Write a test that fails on
  the current tree first** — an unreachable block is exactly the defect a passing
  suite cannot see.
- **[Phase 4, C-A]** Add a lint rule or fitness test for statements following a
  `try` whose every branch terminates. → This defect class is invisible to
  coverage when the enclosing loop is itself exercised, which is why it survived.
- **[Phase 2, `api/dependencies.py:708`]** Either wire `check_preset_access` as a
  `Depends(...)` or delete it and every reference to it. → Today a source comment
  and `docs/plans/audit-remediation-2026-09-08.md:228` both cite it as a live
  entitlement gate. An inert gate that reads as active is worse than no gate.
- **[Phase 4, risk 2]** `router.py:585-588,598-601,621-624,634-637` → make total
  fallback exhaustion raise, or return a value the caller must destructure. →
  This is a fourth instance of the "signal and proceed" shape already specified
  for C-1/C-2/C-3, and belongs in that plan rather than a new one.

### HIGH-IMPACT (next sprint)

- **[Phase 1 / Phase 3]** Reconcile the three architecture ledgers. Pick one rule
  — most likely `.importlinter`'s N-tier, since it is what the code actually does
  — then correct `CLAUDE.md:19` and `test_layer_boundaries.py` to match. → Stops
  new code being reviewed against a rule the tooling permits.
- **[Phase 3]** Ratchet `.importlinter`'s exception count. The counter already
  exists (`ci-local.sh:70`, `--max 59`); flip
  `unmatched_ignore_imports_alerting` from `warn` to `error` so stale entries
  fail rather than accumulate, and delete the four confirmed dead ones (`:66`,
  `:90`, `:100`, and the `:29`/`:56` duplicate).
- **[Phase 5, under-engineering]** `spend_tracker.py` → back `_SPEND` with the
  existing `DistributedStatePort` (Valkey `INCRBYFLOAT` on
  `spend:{subject}:{period}`), which the module's own docstring already
  prescribes. → The monthly ceiling stops scaling with worker count.
- **[Phase 5, dead code]** Delete `security/persuasion_defense.py` (1092 lines,
  zero callers, names classes that do not exist), `feedback_router.py`, and
  `core/search.py`'s inert `_BUILD_PROVIDER` seam — along with the docs that
  describe them as shipped. → ~1500 lines and five false documentation claims
  removed.
- **[Phase 5, temporal coupling]** `domain/preset_core.py:311-317` → make the
  unset-registry case fail loud rather than `return []`. → It currently turns the
  API-key preflight into a silent no-op, and the docstring says this already
  shipped once.
- **[Phase 5, premature abstraction]** Delete `circuit_breaker_port.py`,
  `telemetry_port.py` (duplicated by the one actually used) and `crypto_port.py`;
  type the three `capability_registry` consumers against
  `CapabilityRegistryPort` instead of `Any`, or delete that port too.

### LONG-TERM (architectural evolution)

**Target state: decouple run execution from the HTTP connection.**

Migration sequence, in dependency order:

1. **Fix and enable `WorkflowRunner`.** Its prerequisite is already named in
   `application/pipeline.py:507-513` — the missing
   `PhaseStarted(phase_number=...)`, `PhaseFailed(is_fatal=...)`,
   `EventType.PHASE_QUALITY_CHECKED` and `PHASE_RETRIED` members. *Risk: this is
   a behaviour change on every CLI and headless run; diff a full preset run both
   ways first, as that comment instructs.*
2. **Delete the duplicate engine** at `api/execution/pipeline.py:293-560` once
   step 1 lands, decomposing the 690-line `execute_run`. *Risk: highest in this
   plan — it is the production path. Do it only after step 1 has run in
   production.*
3. **Move run execution behind a queue.** The event store already exists, and
   `infrastructure/documents/index_queue.py` is already in-tree as a
   bounded-worker model (it was introduced to replace uncapped per-upload
   `create_task`). *Risk: changes the SSE contract from "run dies with the
   connection" to "reconnect and resume" — a user-visible improvement, but a
   client change.*
4. **Consolidate persistence onto one engine**, or make the SQLite stores
   switchable the way `event_store.py:846-856` already is. *Risk: `usage_quotas`
   has two writers with different lock orders; sequence that table first and
   alone.*

### SWITCHING TRIGGERS

- **More than one backend replica in production** → every per-process structure
  in Phase 3 becomes a correctness bug rather than a scaling limit. `_SPEND`,
  `_provisioned_user_ids` and `TenantManager` break first.
- **Neuro L1/L2 exceeding one node's disk, or any need for shared memory across
  nodes** → the per-tenant local-file design (`neuro/server.py:179-184`) must
  become a network store; the `TenantManager` docstring already flags the
  divergence.
- **A second `PixelScrubberPort` or `EncryptionPort` implementation appearing** →
  those single-implementation ports stop being premature and should be kept.
- **Sustained runs longer than an SSE connection can hold** → forces step 3 above
  regardless of load.
- **Any regulatory requirement for auditable spend caps** → forces the
  `spend_tracker` change immediately rather than next sprint.

---

## Method and limits

Evidence was gathered by three parallel read-only agents plus direct
verification. Every finding labelled CRITICAL was re-verified independently in
the main session rather than accepted from an agent report:
`api/execution/pipeline.py:481-520` was confirmed by parsing the module, checking
that all three branches of the enclosing `try` terminate, and reading the column
offsets; `WORKFLOW_RUNNER_ENABLED` and the `TypeError` prerequisite were read
verbatim at `core/settings.py:121-122` and `application/pipeline.py:501-513`;
`check_preset_access` and `spend_tracker` were confirmed by grep and by reading
their bodies.

Not covered: `ui-next/` (out of scope), runtime profiling, load testing, and
whether hosted CI currently executes. `lint-imports` was not run, so `[UNKNOWN]`
whether grimp reports indirect cycles beyond the four found by inspection.
