# Remediation Plan: Architecture Score 4/10 → >9/10

**Baseline:** ARCH-AUDIT-V2, 2026-08-20. Score **4/10** — 1 CRITICAL, 7 HIGH, ~7 MEDIUM.
**Target:** **>9/10** = "All layers correctly separated, patterns consistent, observable, testable, scalable."
**Supersedes:** `architecture-score-8.5-remediation-plan.md` (lower bar, superseded 6/10 baseline, WS1–WS2 already ✅) and `security-remediation-plan.md` (Phase 0–1 container sandbox — **already implemented**, see §1.0).

Every item cites the finding it closes. Items already done are listed once, in §0.0, and never re-litigated.

---

## Why the score fell from a claimed 8.5 to a measured 4

Not regression. Three separate causes, and telling them apart matters for sequencing:

1. **New findings the earlier audit never reached.** The event-store single-writer bottleneck (CRITICAL), the `domain ↔ application` import cycle, duplicate `asyncpg` pools, and the entire CI-enforcement collapse were not in the 6/10 baseline.
2. **The earlier plan's own success is invisible to the rubric.** WS1/WS2 genuinely closed the registry bypass. That removed one HIGH. It did not touch the seven others.
3. **Enforcement was never actually load-bearing.** Every gate the 8.5 plan relied on to hold its gains is dead (§0.1). A score with no enforcement is a snapshot, not a property.

**The core lesson, and the organizing principle of this plan: the previous plan optimized the codebase and left the ratchet broken.** Phase 0 is therefore not throat-clearing — it is the only phase whose absence makes every other phase temporary.

---

## §0.0 Already done — do not redo

Verified present in the working tree as of this audit:

| Work | Evidence | Source plan |
|---|---|---|
| Model-registry port + DI at 3 composition roots | `core/ports/model_registry_port.py`; `scripts/check_no_registry_bypass.py` passes | 8.5 WS1 |
| AST guard against registry bypass | `scripts/check_no_registry_bypass.py:20-21,47` | 8.5 WS2 |
| **Container execution sandbox — complete and production-enforced** | `infrastructure/execution/container_sandbox.py:25`; `sandbox_worker/app.py`; `core/ports/code_executor.py:56` | security-plan Phase 0–1 |
| Fail-closed default executor (Null Object) | `NoopExecutor`; `EXEC_SANDBOX_ENABLED` defaults `false` (`core/settings.py:326`) | security-plan Phase 0 |
| Import-time production guard on sandbox mode + worker token | `core/settings.py:458-469` | security-plan Phase 1 |
| Container hardening | `docker_runner.py:48-67` — `--network none`, `--read-only`, `--user 65532`, `--cap-drop ALL`, `no-new-privileges`, `--pids-limit 64`, tmpfs `noexec,nosuid` | security-plan Phase 1 |
| Tenant isolation from credentials, not request body | `neuro/server.py:264-286`, `_safe_agent_id` at `neuro/config.py:344-356` | — |
| SQLi regression closed in `ErrorStore` | `_safe_int` guards all five `.format()` sites (`error_store.py:148-163`) | — |
| Account keys hashed; metadata encrypted; versioned crypto dispatch | `persistence/auth_store.py:29,95-96`; `security/encryption.py` | — |
| No BYOK — provider keys env-only, never persisted | `routes/keys.py:41,55-58` | — |

**Correction to the published audit:** its Phase 4 "Tool execution" paragraph described the executor as a same-host subprocess with no container isolation. That characterizes `SubprocessExecutor` (legacy, dev-only), not the production path. `ContainerExecutionSandbox` is the approved boundary, is wired, is health-gated per call (`container_sandbox.py:66-73`), and is enforced in production. The audit artifact has been corrected.

---

## Phase 0 — Restore enforcement (prerequisite; blocks all durability)

**Finding:** every CI gate is dead. 38/38 recent workflow runs failed in ~3s — *"recent account payments have failed"*. `gh api .../branches/main/protection` → **403, "Upgrade to GitHub Pro or make this repository public"**: on a private free-plan repo, **no status check can ever be marked required**. The only executing gate today is an untracked `.git/hooks/pre-commit` secret scan, plus `scripts/ci-local.sh` when someone remembers to run it.

**Paradigm: architectural fitness functions** (Ford/Parsons/Kua, *Building Evolutionary Architectures*). An architecture characteristic that is not continuously, automatically verified is an aspiration. Every subsequent phase in this plan ends in a fitness function, and none of them mean anything until this phase lands.

| # | Action | Closes | Size |
|---|---|---|---|
| 0.1 | Restore Actions billing. **Then** either make the repo public or move to GitHub Pro/Team so branch protection can require checks. Until one of those, no gate is enforceable — treat 0.2 as the real contract. | dead CI | S (billing) / decision (plan tier) |
| 0.2 | Version the hooks: add `.pre-commit-config.yaml`, set `core.hooksPath` to a tracked `.githooks/`, move the secret scan there, add `scripts/ci-local.sh` as a **pre-push** hook. Hooks currently live untracked in `.git/hooks/` and do not survive a clone. | untracked hooks | M |
| 0.3 | Delete `[tool.pytest.ini_options]` from `pyproject.toml:23-30` or merge it into `pytest.ini`. `pytest.ini` takes absolute precedence, so `xfail_strict = true`, `asyncio_mode`, `timeout`, and `filterwarnings` are all **silently inert**. | dead config | S |
| 0.4 | Fix `get_imports` in `tests/architecture/test_layer_boundaries.py:60-74` to walk `ast.Import` as well as `ast.ImportFrom`. Today a plain `import reasoner.api` defeats the layer test entirely. Copy the correct pattern from `scripts/check_no_registry_bypass.py:30-31`. | blind fitness function | S |
| 0.5 | Replace the three `@pytest.mark.xfail` god-file caps (`test_layer_boundaries.py:125,135,145`) with real thresholds pinned at current line counts. With `xfail_strict` inert (0.3), these currently fail *open in both directions* — they never fail, and they never notice success either. | disarmed caps | S |
| 0.6 | Turn the import-linter **budget into a ratchet**: fail when `COUNT < MAX` too (forcing `MAX` down), and count semantically via `lint-imports --output` rather than `grep -c '\->'`, which counts arrows inside prose comments. Remove the 5 free slots (60 actual vs `MAX=65`, `pr-architecture.yml:31-45`). | budget ≠ ratchet | M |
| 0.7 | Set `unmatched_ignore_imports_alerting = warn` (currently `none`, `.importlinter:11`) so stale exceptions surface and the list can self-clean instead of permanently occupying budget. | undead exceptions | S |
| 0.8 | Reconcile coverage: PR gate is **30%** (`coverage.yml:56-58`), the 60% gate never runs on a PR (job guard `self-healing-ci.yml:112-115` is schedule/dispatch-only), README badge hardcodes `~70%` as a static shield (`README.md:10`). Pick one number, gate on it, generate the badge from a real run. | three contradictory numbers | M |
| 0.9 | Run `mypy` over `src/` — today it runs on exactly one file (`test.yml:39-41`). Align CI's `ruff --select B,F821` with the configured `pyproject.toml:20-21` profile (`E,F,I,N,W,UP`); the two sets are currently **disjoint**, so the configured lint profile never executes. | decorative type config | M |
| 0.10 | Add per-package coverage floors for `domain/` and `core/` specifically. A global percentage lets newly-written clean code hide behind old covered code — exactly the failure mode Phase 4 would otherwise walk into. | global-only coverage | S |

**Exit criterion:** a deliberately-introduced `import reasoner.api` inside `domain/`, a 900-line file, and a hardcoded secret each fail a gate that runs without human memory.

---

## Phase 1 — Security

Ordered by exploitability × blast radius, not by severity label. Depends on Phase 0 only for durability, not for correctness — start in parallel.

### 1.1 Global rate-limit middleware — HIGH

`check_rate_limit` is a **per-route `Depends`**, not middleware. Registered middleware (`api/__init__.py:336,340,354,979,984`) covers security headers, audit, memory, timeout — **no rate limiting**. Every route must remember to opt in, and §1.2's endpoints demonstrably did not.

**Pattern: Decorator/middleware backstop + explicit opt-out.** Add `RateLimitMiddleware` applying a conservative global bucket; routes needing looser or tighter limits declare it explicitly. Inverts the default from *fail-open on forgetfulness* to *fail-closed by construction*.

This single change removes the entire class of omission in §1.2 — do it first.

### 1.2 Authenticate unmetered LLM-cost endpoints — HIGH / MEDIUM

| Endpoint | Location | Missing |
|---|---|---|
| `POST /api/suggestions` | `routes/widgets.py:78-79` | **no auth, no rate limit, no CSRF** — calls an LLM |
| `POST /api/widget/execute` | `routes/widgets.py:94-97` | CSRF only |
| `POST /api/gate` | `routes/gate.py:20-26` | CSRF only — calls `decide_route` (LLM) |
| `POST /api/estimate` | `routes/estimate.py:17-20` | CSRF only |
| `GET /api/weather`, `/api/stocks`, `/api/discover` | `routes/legacy_widgets.py:16,31,70` | nothing |
| `POST /api/search` | `api/__init__.py:716` | no CSRF, no credit reservation — burns search-provider quota |
| `GET /api/websocket/stats` | `routes/websocket.py:106` | no auth |

`/api/suggestions` is the worst: fully open and LLM-backed. Anonymous cost amplification.

Apply the same dependency stack the four inline routes already use correctly (`api/__init__.py:626-638`) — that pattern is right, it just wasn't propagated.

### 1.3 Re-validate every redirect hop (SSRF) — HIGH

`security/url_validator.py` is genuinely thorough — scheme allowlist, 16 blocked CIDRs including `169.254.0.0/16`, all resolved IPs checked, unresolvable → block. **But the check is pre-flight only, and the fetch then follows redirects**: `scraper.py:45`, `image_generation.py:239` both pass `follow_redirects=True`. An attacker-controlled public host returning `302 → http://169.254.169.254/latest/meta-data/` reaches cloud metadata.

**Fix once, in a shared client factory** covering all three call sites: either `follow_redirects=False` plus a manual loop that re-runs `is_safe_url` per hop, or an httpx event hook doing the same. Do not patch three call sites independently — that's how the fourth one (`search_phases.py:45`, redirects on, no validation at all) happened.

### 1.4 Make unsanitized prompt input unrepresentable — HIGH

Five request fields reach LLM prompts without `sanitize_for_prompt`: `SearchRequest.query` (`schemas.py:29-42`), `GenerateImageRequest.prompt` (`:194`), `ContextAnalysisRequest.problem`/`.context` (`:256-257`), `SuggestionRequestModel.query`/`.chat_history` (`:287-289`, **no validator at all**), and `RunRequest.conversation_history`.

**Pattern: Parse, don't validate.** Do not add five more validators — that repeats the mistake at a larger radius. Define a `SanitizedPrompt` newtype whose only constructor runs the sanitizer, and type every prompt-bound field as it. Forgetting to sanitize then becomes a type error rather than a silent gap. This is the same structural move as §1.1: convert a discipline problem into a construction problem.

**Also fix the sanitizer's own honesty.** `sanitize_for_prompt` (`core/sanitization.py:185-225`) is a **regex denylist** of 11 patterns — it catches `ignore previous instructions` and `[INST]`, and misses paraphrase, non-English, encoded, and indirect injection. It is a speed bump, and the codebase treats it as a boundary. Two consequences to fix alongside:
- It raises `ValueError` on match → **422 false-positive DoS**. Any user discussing prompt engineering (`system:`, `assistant:`) is locked out.
- `_check_suspicious_patterns` warnings are computed and **discarded at all 8 call sites** (`v, _ = sanitize_for_prompt(v)`). Route them to telemetry; they are the only injection signal currently produced.

### 1.5 Delete `SubprocessExecutor` — HIGH

The container path is complete, tested (`tests/integration/test_sandbox_escape.py`), and production-enforced. `SubprocessExecutor` remains importable and reachable whenever `ENVIRONMENT != production` (`application/flows/services.py:59-61`), so staging runs LLM-authored code on the API host behind `check_code_safety` — a **name-based denylist over a dynamic language**, trivially bypassed by `getattr(__builtins__, 'ev'+'al')` or `().__class__.__base__.__subclasses__()`, and self-described as defence-in-depth only (`core/code_safety.py:112-113`).

Its sole remaining function is to be a foot-gun in staging. Delete the adapter; keep `NoopExecutor` as the non-container default.

### 1.6–1.9 Remaining gaps

| # | Gap | Location | Sev |
|---|---|---|---|
| 1.6 | **Delimiter fences unescaped.** `_wrap_external_content` interpolates without stripping the terminator from the payload — scraped content or PoT stdout containing `<<<END_EXTERNAL_CONTENT>>>` closes its own fence. | `phases/_shared.py:135-142` | MEDIUM |
| 1.7 | **PoT stdout fenced but never scrubbed.** Correction to the audit: it *is* wrapped (`phases/pot.py:59-60`), so "byte-cap only" was wrong. But no `sanitize_for_prompt`, no Unicode carrier scrub. | `cognitive_phases.py:283` | MEDIUM |
| 1.8 | **DNS-rebinding TOCTOU.** Validator and httpx resolve independently; short-TTL DNS can return public to one and private to the other. Pin the validated IP for the fetch. | `url_validator.py:45-51` | MEDIUM |
| 1.9 | **Anonymous tenant namespace collision.** Anonymous keys are `a-{agent_id}` (`neuro/server.py:285`); anonymous A can recall or poison anonymous B's memory by guessing a conversation id. Authenticated `u-{owner}-{id}` scoping is correct and unaffected. | `neuro/server.py:264-286` | MEDIUM |
| 1.10 | **`persuasion_defense.py` — 1092 lines, zero call sites.** Its docstring names an insertion point that does not exist; the only reference is a re-export shim (`reasoner_persuasion_defense.py:2`). Also a *different threat model* — manipulative generated output, not prompt injection. **Wire it or delete it.** Unreferenced security code is worse than absent code: it reads as coverage that does not exist. | `security/persuasion_defense.py` | LOW (high misleading-ness) |
| 1.11 | `seccomp_profile` param exists (`docker_runner.py:76`) but `app.py:96-101` never passes one — only Docker's default profile applies. Safety tiers `DANGEROUS`/`SUSPICIOUS` are computed then discarded (`code_safety.py:60-68`). | — | LOW |

**Deliberately not doing:** extracting `CipherSuite` (`core/ports/crypto_port.py:49`). It is dead (§5.5 deletes it). The crypto that exists is modern and correctly versioned; adding an abstraction over two in-class implementations is the premature-abstraction pattern this plan is trying to reduce.

**Fitness functions:** a test asserting every route in `api/routes/` carries an auth-or-explicitly-public marker; a test asserting no prompt-bound field accepts `str`; an SSRF test following a redirect chain into `169.254.169.254`.

---

## Phase 2 — The CRITICAL bottleneck: event store

**Finding:** all event-store I/O for all concurrent runs funnels through one `ThreadPoolExecutor(max_workers=1)` **plus** a `threading.Lock` held for the full call duration (`event_store_connection.py:29-32,50-59`).

Two clarifications that change the fix:

1. **The lock is provably redundant.** `max_workers=1` already serializes access to the shared connection. `check_same_thread=False` (`:42`) exists only because `init_db` runs on the caller's thread. Removing the lock alone changes nothing; raising the worker count alone is unsafe without a real pool. Fix both together.
2. **The hot path is not the event bus.** `application/event_bus/bus.py:436-447` is queue-decoupled and fine. The real load is `api/sse_utils.py:62-77`, called with a bare `await` from `api/execution/pipeline.py` at `:256, :416, :456, **:598 (PHASE_COMPLETED — once per phase)**, :658, :676`. Its docstring says "fire-and-forget", but that only means exceptions are swallowed — **the call is awaited**, so every phase boundary of every concurrent run serializes on one thread.

**And the Postgres path already exists but is broken as wired.** `EVENT_STORE_BACKEND` (`core/settings.py:131-133`) already defaults to `postgres` when `DATABASE_URL` is set in production. Three blockers:
- `event_store.py:832` constructs `PostgreSQLEventStore` and **never awaits `initialize()`** → `self._pool` stays `None` → `AttributeError` on first write. The correct factory `initialize_postgres_store` (`postgres_store.py:1033`) is never called anywhere in `src/`.
- Method-parity gap: Postgres lacks `get_aggregate_state`, `count_events`, `get_events_since`.
- `close()` is async on Postgres (`:1004`), sync on SQLite (`:804`); `reset_event_store()` calls it unawaited.

So the CRITICAL fix is **repair-and-enable, not build-from-scratch**.

| # | Action | Size |
|---|---|---|
| 2.1 | Extract `EventStorePort` Protocol (11 methods — none exists today; `get_event_store() -> Any` at `event_store.py:825` is the only reason the swap typechecks). Replace concrete deps in `data_eraser.py:11,29` and `routes/gdpr.py:12,31`, and the `hasattr`/`isinstance` duck-typing in `snapshots.py:98,122,272,316,334`. | M |
| 2.2 | Repair the Postgres adapter: await `initialize()` via the real factory, add the 3 missing methods, unify `close()` as async. Document the plaintext-JSON (SQLite) → encrypted (`postgres_store.py:282`) migration path — there is none in-repo today. | M |
| 2.3 | Replace the single-worker pattern with one shared pooled-connection abstraction (**Repository + Unit of Work**). Apply to all four stores — `error_store.py:79-88`, `feedback_store.py:71-80`, `telemetry_store.py:63-70` each independently clone the identical anti-pattern. A one-off patch to `event_store_connection.py` leaves three copies. | L |
| 2.4 | Decouple the SSE hot path: route `_persist_event` through the already-working queue-decoupled bus rather than an inline `await` per phase. | M |
| 2.5 | Rewrite `tests/test_event_store_concurrency.py:140` — it asserts on `store.conn._executor` internals and **will break on any correct refactor**. Re-express as a behavioural throughput/consistency assertion. Add the missing `snapshots.py` test file; `SnapshotManager`'s replay/gap-detection (`snapshots.py:218-227`) is entirely uncovered. | M |

**Also clean up while in here:** `EventStore._init_db` (`event_store.py:55-122`) is a divergent dead copy of the live schema; `orchestrator.py:30` imports `get_event_store` and never uses it; `routes/gdpr.py:31` constructs a *fresh* `EventStore` (second connection + second executor on the same file); `list_aggregate_ids_for_user` (`:622`) opens yet another connection via `PipelineOwnershipRepository`.

**Fitness function:** a load test asserting p99 event-write latency stays flat from 1 → 50 concurrent runs.

---

## Phase 3 — Layer purity

Drives `.importlinter`'s 60 exceptions toward zero. Each item removes a documented carve-out.

| # | Violation | Fix | Pattern |
|---|---|---|---|
| 3.1 | `domain/pipeline_state.py:699,704,710` imports `application.services.pipeline_service`, which imports `PipelineState` back — a real cycle, avoided only at import time by function-local imports, tracked in `.importlinter:101` as "deprecated lazy compat delegations". | Move `to_dict`/`to_context_dict`/`_from_dict` fully into `PipelineSerializationService`. Leave `PipelineState` a pure data holder. | Separated interface |
| 3.2 | `application/handlers/handlers.py:263,547` imports `reasoner.api` (one static, one `importlib`). Upward dependency. | Invert via an injected port; the dynamic import is hiding the coupling from static analysis, not removing it. | Dependency inversion |
| 3.3 | `application/services/anonymous_trial_policy.py:23,63` raises `fastapi.HTTPException`. Any non-HTTP caller (CLI, `headless.py`) gets an exception type that means nothing. | Raise a domain error; translate at the API edge via the existing `register_exception_handlers`. Prefer an explicit `Result` for expected policy denials — a quota denial is a normal outcome, not an exception. | Railway-oriented / Result |
| 3.4 | `application/flows/search_phases.py:11,45` instantiates `httpx.AsyncClient` directly. | Behind `SearchServicePort`. Fold in the §1.3 redirect guard so the port is the one place SSRF policy lives. | Ports & adapters |
| 3.5 | `health_service.py:82-89` and `api/dependencies.py:19,72-86` each create an independent `asyncpg.create_pool`, bypassing `postgres_store.py`. Three pool lifecycles for one database. | Consolidate onto the §2.3 shared pool. | Repository |
| 3.6 | `application/event_bus/bus.py:25` — the one **non-lazy** `application → infrastructure` import. | Subscriber registration at the composition root, not at module import. | Composition root |

Then ratchet `MAX` down as each carve-out is deleted (0.6 makes this automatic).

---

## Phase 4 — Domain model: anemic → rich

**Finding:** `PipelineState` (`domain/pipeline_state.py:231-711`) is ~25 near-identical property pass-throughs over a generic dict bag (`jury_guidelines`, `debate_rounds`, `scientific_state`, … all delegating to `MethodState.get/.set`), plus trivial mutators and serialization helpers. **Zero invariant enforcement** — nothing prevents `final_solution` being set before `candidates` exist. All 7,181 lines of real logic live in `application/flows/*` operating on the bag from outside.

This is the largest single lever on "patterns consistent" in the rubric, and the highest-risk phase. Do it last among the structural phases, behind Phase 0's fitness functions and Phase 2's tests.

| # | Action | Pattern |
|---|---|---|
| 4.1 | Replace the ~25 dict pass-throughs with typed per-method value objects. The `dict[str, Any]` + `.get()` convention exists to keep `--resume` working with older state files — preserve that by versioning the deserializer, not by keeping the whole model untyped. | Value objects |
| 4.2 | Enforce invariants at construction rather than by convention. | Parse, don't validate |
| 4.3 | **Resolve the immutability question.** `PhaseOutput.apply_to` (`pipeline_state.py:186-228`) was built to apply deltas immutably, then defeated at the highest-traffic call site: `perspective_phases.py:181` passes `mutated_in_place=True`, making the reducer a no-op, and `:234-235` mutates `state.candidates`/`state.errors` directly. Every other phase mutates in place and returns `None`. Either finish the migration and delete the flag, or formally retire `PhaseOutput` and document `PipelineState` as intentionally mutable. **Do not leave it half-built** — a half-finished abstraction misrepresents the actual update model to every reader. | Functional core, imperative shell |
| 4.4 | Model phase progression as a discriminated union rather than ~60 independently-optional fields, so "critique before generation" cannot be constructed. This also kills the temporal coupling at `research_phases.py:25-60` ↔ `prism_research.py:168-182`, where a downstream phase reads state an upstream phase populates only when a settings flag is on, with no assertion and no log on the silent-default path. | Make illegal states unrepresentable |

**Recommendation:** 4.1 + 4.2 + 4.3 are required for >9 ("patterns consistent"). 4.4 is the highest-value and highest-risk item in the plan; sequence it as its own change with Phase 2's tests already green.

---

## Phase 5 — Decompose god modules

| # | Target | Action |
|---|---|---|
| 5.1 | `api/__init__.py` (1,008 lines) — composition root **and** four inline business handlers at `:626, :689, :716, :792` | Move handlers to `api/routes/`. Leaves a pure composition root and un-`xfail`s the 250-line cap from 0.5. |
| 5.2 | `ui-next/src/app/chat/page.tsx` (1,299 lines); `handleSubmit` alone is ~648 lines (`:293-941`) mixing WebSocket setup, 15+ `useState`, gate logic, and JSX | Extract a data/WebSocket hook + presentational components; split `handleSubmit` into named sub-handlers. |
| 5.3 | `application/services/serializers.py` (1,129 lines) — `_ser_2`…`_ser_5`, each 138–227 lines branching across unrelated preset types | Strategy dispatch keyed by phase, one small module per serializer. |
| 5.4 | `application/pipeline.py` (748 lines) — ~30 one-line delegators, documented at `:237-240` as compat shims for `api/routes/context.py` | Migrate remaining callers to the `flows/*` functions directly; delete the delegators. Completes the WorkflowStrategy refactor the code already announces. |
| 5.5 | Five dead ports — `CircuitBreakerPort`, `ProviderRegistryPort`, `CipherSuite`, `TelemetryStorePort`, `TranslationPort` — zero references outside their own definitions | **Delete.** Ports earn their place by having a second adapter or a real seam. `FileSearchPort` and `ModelRegistryPort` (one impl each) stay — both are genuine boundaries. |

Also: `postgres_store.py` (1,046), `preset_registry.py` (944), `api/dependencies.py` (714), `persuasion_defense.py` (1,092 — deleted by 1.10), `image_generation.py` (1,077). Split by cohesion, not by line count; several may be legitimately large.

---

## Phase 6 — Observability

The rubric's "observable" leg is the one this plan cannot claim on structure alone.

- Structured logging with a run-scoped correlation id spanning HyperGate → phases → LLM calls → event store.
- Prometheus/OTel counters on the paths Phase 2 touches: event-write latency, queue depth, per-model semaphore saturation (`router.py:254-264`), circuit-breaker state transitions.
- Route the discarded injection-heuristic warnings from §1.4 into telemetry.
- Route the discarded `DANGEROUS`/`SUSPICIOUS` safety tiers from §1.11 into telemetry.
- Langfuse is already wired and production-required (`api/__init__.py:39-56`) — extend rather than add a parallel stack.

---

## Scoring ledger

| Phase | Closes | Score effect |
|---|---|---|
| 0 | Dead CI, blind fitness function, inert config | **Gates the rest.** No direct points; without it every gain below is a snapshot |
| 1 | 4 HIGH (rate limit, unauth LLM endpoints, SSRF redirect, ungated prompts) + `SubprocessExecutor` + 4 MEDIUM | −5 HIGH |
| 2 | The CRITICAL | −1 CRITICAL → clears the "no critical violations" bar |
| 3 | 3 HIGH (domain cycle, app→api, HTTPException) + 3 MEDIUM | −3 HIGH |
| 4 | 1 HIGH (anemic model) + temporal coupling + immutability ambiguity | −1 HIGH; carries "patterns consistent" |
| 5 | 2 HIGH (god modules) + premature abstraction | −2 HIGH |
| 6 | — | Carries "observable" |

Phases 1–5 close 1 CRITICAL and all 7 HIGH. **>9 requires Phase 0 landing too** — the rubric's top band describes properties, and a property that nothing verifies is a claim.

---

## Sequencing

```
Phase 0 ─────────────────────────────────────────►  (start immediately, blocks durability)
   │
   ├── Phase 1 (security) ──────────────►           (parallel; 1.1 first — it subsumes 1.2)
   │
   ├── Phase 2 (event store) ───────────►           (parallel; 2.1 port first)
   │        │
   │        └── Phase 3 (layer purity) ──►          (3.5 needs 2.3's pool)
   │                    │
   │                    └── Phase 4 (domain) ──►    (needs 2.5 tests green)
   │
   └── Phase 5 (god modules) ───────────►           (independent; good parallel filler)
                                    │
                                    └── Phase 6 ─►  (last; instruments the finished shape)
```

**Critical path:** 0 → 2 → 3 → 4. Phases 1 and 5 are genuinely parallel.

---

## Explicitly out of scope

- **Rebuilding code-execution isolation.** It exists and is good (§0.0). The work is deleting the legacy adapter, not adding a sandbox.
- **Extracting `CipherSuite`.** Delete it (5.5).
- **A second LLM registry or file-search adapter.** `ModelRegistryPort`/`FileSearchPort` stay as-is; they are seams, not speculation.
- **Migrating off SQLite entirely.** Postgres for the event store in production (§2.2); SQLite stays correct for local and CLI use.
- **Rewriting `sanitize_for_prompt` into a model-based injection classifier.** Out of proportion. Fix the type-level gap (§1.4), stop treating a denylist as a boundary, and instrument it.

---

## Switching triggers

- **Repo stays private on the free plan** → branch protection is impossible; `.githooks/` + `ci-local.sh` (0.2) is not a stopgap, it is the permanent enforcement contract, and should be documented as such.
- **Concurrent run volume grows before Phase 2 lands** → 2.4 (decouple the SSE hot path) alone buys most of the headroom and can ship ahead of 2.1–2.3.
- **A second event-store backend beyond SQLite/Postgres appears** → `EventStorePort` (2.1) is already the right seam; nothing changes.
- **`--resume` compatibility with old state files gets dropped** → Phase 4 simplifies sharply; the `dict[str, Any]` convention exists almost entirely to serve it.
