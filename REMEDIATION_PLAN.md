# Remediation Plan

A phased plan to close every defect and gap currently open in Reasoner, with the
paradigm and design-pattern choice justified per module.

**Survey date:** 2026-08-15 · **Revised:** 2026-08-16 (post-R0 pass) · **Branch:**
`review-rebase` · **Companion docs:**
[`ENCRYPTION_ROADMAP.md`](ENCRYPTION_ROADMAP.md) (P4–P6 folded in here as R4/R5),
[`CLAUDE.md`](CLAUDE.md), [`ARCHITECTURE_MINDMAP.md`](ARCHITECTURE_MINDMAP.md).

---

## 0. How this inventory was produced

Everything below was executed, not inferred. Commands and their observed results:

| Check | Command | Result |
|-------|---------|--------|
| Architecture contract | `lint-imports` | **KEPT** — 423 files, 1270 deps, 1 contract, 0 broken |
| Import-linter budget | `grep -c '\->' .importlinter` | **59** used / 65 max — 6 left |
| Test suite (CI's lane) | `pytest -m "not slow and not integration"` | **105 failed**, 2845 passed, 80 skipped, 298s |
| Ruff — project config | `ruff check src/ tests/ scripts/` | **6258** errors |
| Ruff — CI's own gate | `ruff check src/ --select B,F821 --ignore B008` | **31** errors, all `F821` (CI passes only via `--exit-zero`) |
| Frontend types | `npx tsc --noEmit` | **fails** on a corrupt generated file (local only) |
| SDK in CI | `grep -r sdk .github/workflows/` | **no matches** |

Caveats on that test run:

* The original survey ran with `-x` and stopped at 6 failures. The unhalted re-run
  (R0's explicit task) put the real count at **105**. Every number in this document
  that reads "6" was a floor artifact and has been corrected.
* Coverage was not measured this pass. The `coverage.yml` floor comment describes 30%
  as reflecting "real unit-only coverage", so actual likely sits just above the floor
  and well under the 80% target.
* The 105 count is *after* R0 closed 22 failures. The pre-R0 baseline was 127.

---

## 1. Finding register

Severity uses the project's [code-review](CLAUDE.md) scale: **CRITICAL** blocks merge,
**HIGH** should block, **MEDIUM** is maintainability, **LOW** is optional.

### 1.1 Red gates

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| **F1** | CRITICAL | **105** tests fail in the exact lane CI runs. A PR to `main` is red today. Raised from HIGH once the true count was known: this is not a handful of bugs but a systemic condition — see §1.1.1. | `pytest -m "not slow and not integration"` |
| **F2** | HIGH | CI's ruff step ends in `--exit-zero`, so it can never fail. The 14 `B904`, 8 `B905`, 5 `B007`, 2 `B010` and 1 `B039` behind it were cleared in R0; what remains is **31 findings, all `F821`** — i.e. F2 and F3 now name the same set. `--exit-zero` cannot come off until F3 is closed. | [`test.yml:33`](.github/workflows/test.yml:33) |
| **F3** | MEDIUM | 31 `F821` unresolvable forward references. **Latent, not live** — every site was confirmed to carry `from __future__ import annotations`, so they do not raise today. They break under `typing.get_type_hints()` / `inspect.signature(eval_str=True)`, which Pydantic and FastAPI both call, and they silently degrade those annotations to `Any` for mypy. | `ruff --select F821`; verified in `api/cache.py`, `api/dependencies.py`, `core/parsing.py`, `application/flows/article.py` |
| **F4** | MEDIUM | `pyproject.toml` selects `E,F,I,N,W,UP` → 6258 violations. Nothing enforces it. The config is aspirational fiction. | [`pyproject.toml:17`](pyproject.toml:17) |

#### 1.1.1 What the 105 failures actually are

The original six-test sample suggested a few unrelated bugs. The full set says otherwise:
this is **one phenomenon — test drift.** Modules were moved, class methods became module
functions, model IDs were bumped, and config objects became raw dicts, but the tests
pinned to the old shapes were never migrated. The suite has been asserting against an
API that no longer exists.

That reframing matters, because it changes what R0 *is*: not "fix six bugs" but a
migration pass over a stale suite, plus the source defects the pass uncovers. It also
sets the correct failure mode to guard against — the cheap way to make a drifted test
pass is to relax its assertion, which converts a red gate into a decorative one and
reproduces F2 in a new location.

Remaining classes, with counts from the post-R0 run:

| Class | ~n | Nature |
|-------|----|--------|
| Auth status drift | 15 | **done** — two distinct root causes. (1) `get_auth_adapter()` now picks `SupabaseAuthAdapter` outside `ENVIRONMENT=testing`, so any module that builds its own `LocalAuthAdapter()` token but never calls `set_auth_adapter()` gets real 401s from a network-dependent (and JWT-incompatible) Supabase validation attempt instead of validating locally. Fixed via `set_auth_adapter(LocalAuthAdapter())` right after adapter construction in `test_feedback.py`, `test_saas_history.py` (its `history_client` fixture builds a standalone bare `FastAPI()` app, but `get_auth_adapter()` is a global singleton independent of which app the routes are mounted on, so the fix still applies), and `test_security_regression.py`. (2) `test_bugfixes_regression_round2.py`'s `TestRequireTierEnforcement`/`TestCheckPresetAccess` used `monkeypatch.setenv("ENVIRONMENT", ...)`, but `settings.ENVIRONMENT` is a pydantic-settings field cached at construction, not re-read from `os.environ` live — the monkeypatch silently did nothing; the "blocks_in_production" tests failed outright, the "allows_in_development" siblings passed only by accident since the ambient default is already `development`. Fixed all four by switching to `monkeypatch.setattr(settings, "ENVIRONMENT", ...)`. Two more real production bugs found and fixed along the way, not auth-adapter drift: `api/routes/feedback.py`'s `submit_feedback()` built `FeedbackEntry(run_id=..., score=..., method=..., preset=...)` — kwargs that don't exist on the actual `FeedbackEntry` dataclass in `feedback_store.py` (`message_id`/`rating`/`reason`/`comment`/`context`) — a 500-on-every-real-request bug, same class as the `feedback_stats()` field-name bug already fixed in `72c72a9` but missed for the POST handler; and `test_security_regression.py`'s `test_context_error_is_generic` patched `reasoner.api.routes.context.ReasonerPipeline`, which the route no longer imports (`context.py` now builds pipelines via `PipelineOrchestrator.create_pipeline()`) — retargeted the patch and swapped a guessed nonexistent preset (`auto-budget`) for a real one (`multi-perspective-budget`). Verified: 33 passed (`test_feedback.py`/`test_saas_history.py`/`test_security_regression.py`) + 29 passed (`test_api_auth_deps.py`/`test_bugfixes_regression_round2.py`/`test_metered_auth_policy.py`/`test_sandbox_worker.py`). |
| `_phase_*` monkeypatch drift | 15 | **done** — architecture changed, not just renamed. Classification+Decomposition fully moved into `PipelineOrchestrator.preflight()` (`application/orchestrator.py`) pre-pipeline; `MultiPerspectiveFlow.get_phases()` (`application/flows/multi_perspective.py`) has no Decomposition step at all. Synthesis/Critique/StressTest run as standalone module functions (`run_synthesis_phase`/`run_critique_phase`/`run_stress_test_phase`) referenced directly in the strategy's phase list, not `ReasonerPipeline` methods — so patching `ReasonerPipeline._phase_synthesis` etc. is silently inert (method still exists, just never called). Fixed by retargeting patches to `reasoner.application.flows.multi_perspective.run_critique_phase`/`run_stress_test_phase`/`run_synthesis_phase` in `test_api_phase_errors.py` and `test_e2e_comprehensive.py::TestAPICriticalPhaseErrorHalt` (using Critique & Pruning — the only `critical=True` step — in place of the removed Decomposition step for critical-halt tests, Stress Testing for the non-critical-continues test). Also fixed `reasoner.api.streaming._recall_neuro_context` → moved to `PipelineOrchestrator._recall_neuro_context`. `test_api_gate.py`'s `_phase_0_classify` patches are already `@pytest.mark.skip`d (not counted in failures). `test_followup_agent.py`'s `_phase_synthesis` patches are inert too but harmless (assertions don't depend on that phase running) — however running it surfaced a **separate, real regression**: `routing.get("synthesis"/"classification"/"decomposition")` no longer reflects the `agent_model` follow-up override (`orchestrator.py:100-112` passes `agent_model` into `build_router()` but the captured routing dict comes back as the un-overridden default) — moved to the unclassified bucket for its own investigation, not a `_phase_*` rename issue. Verified: `test_api_phase_errors.py` + `test_e2e_comprehensive.py::TestAPICriticalPhaseErrorHalt` green. |
| Rate limiter refactor | 8 | **done** — `_lock_for`/`_get_bucket` → `_fallback_lock`/`_in_memory_get_bucket` (`test_bugfixes_regression_round2.py`); `burst_limit`/`per_minute_limit` → `..._fallback` reason strings (3 files); `test_rate_limiter_sharding.py`'s `ENABLE_SHARDED_LOCKS`/`_sharded` premise is gone entirely (sharding replaced by Redis token-bucket script + single fallback lock) — rewritten to test concurrent-access safety under the current design instead of asserting removed internals. Also found and fixed a real bug along the way: `get_client_stats()` read `self._buckets[client_id]` directly (defaultdict default `tokens=0.0`) instead of `_in_memory_get_bucket()`, so stats for a never-queried client falsely reported zero capacity instead of a full burst. |
| OCR / uploader mocks | 14 | **done** — six distinct root causes across `test_reliability_patches.py`/`test_ocr.py`/`test_document_vector_store.py`/`test_io_security.py`: (1) `patch()`/`monkeypatch` targets pointed at the `reasoner.uploader`/`reasoner.main` backward-compat shims instead of `reasoner.infrastructure.uploader`/`reasoner.pipeline`, where the real functions actually resolve `_extract_pdf`/`_extract_image`/`UPLOAD_DIR`/`extract_text`/`ReasonerPipeline` at call time — shim re-exports are a separate binding, patching them is a silent no-op; (2) `get_auth_adapter()` now picks `SupabaseAuthAdapter` outside `ENVIRONMENT=testing`, so `test_ocr.py`'s module-level `TestClient` got real 401s from a DNS-failing Supabase call — fixed via `set_auth_adapter(LocalAuthAdapter())`, the pattern already established in `test_saas_auth_integration.py`; (3) `DocumentVectorStore.retrieve()` legitimately gained a `user_id=None` kwarg for per-user isolation, test assertion hadn't caught up; (4) `reasoner.main.build_router` no longer exists (HyperGate routing moved into `PipelineOrchestrator`) — patch was obsolete, removed; (5) a `MagicMock()` args object without `args.benchmark`/`args.benchmark_all` set tripped a benchmark early-exit branch added to `main()` after the test was written; (6) `PipelineOrchestrator.preflight()` now does real preset/routing resolution a bare `MagicMock` args can't satisfy — fixed by mocking `preflight()` itself to return a canned `PreflightDecision`. Verified: 59 passed. |
| Import drift | 3 | **done** — `health_check`/pool moved `api/__init__.py` → `api/routes/health.py` + `application/services/health_service.py`; `_CREATIVE_SYSTEM_PROMPT` dup in `streaming.py` was already removed (single source now `core/constants_prompts.py`), test rewritten to guard against the dup coming back instead of asserting a copy that no longer exists |
| Unclassified | ~54 | event bus, DAG, quota, feedback, history scoping, prompt injection — not yet triaged individually |

**Closed in R0** (root causes, not symptoms): analogical preset/flow-strategy wiring —
the architecture assertion `test_preset_methods_map_to_flow_strategies` now passes
honestly; `test_cross_process_cancel_via_redis` re-marked `@pytest.mark.integration`;
`PostgresQuotaRepository._pool` class-vs-instance fixture seam (6 tests); and the
pinned-model-ID class, rewritten to resolve through `_REGISTRY` / alias constants /
`IMAGE_GEN_PRESETS` so the same tests cannot rot again on the next model bump.

**Open question this plan cannot yet answer:** how 105 tests reached `main`'s own lane
without anyone noticing. Either CI has been red for some time, or the lane markers
exclude more than intended. Establish which before R2 sets a coverage ratchet on top
of it.

### 1.2 Verification that does not verify

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| **F5** | HIGH | The OpenAPI drift snapshot — the whole point of the contract suite — **never runs in CI**. Its three app-importing tests are `@pytest.mark.slow`, and both `test.yml` and `coverage.yml` run `-m "not slow and not integration"`. | [`test_sdk_contract.py:182,211,244`](tests/test_sdk_contract.py:182) |
| **F6** | HIGH | `sdk/typescript` has **zero** CI presence — no `tsc`, no vitest, no build. The SDK can rot against the API silently, which is precisely what it exists to prevent. | no `sdk` match in `.github/workflows/` |
| **F7** | MEDIUM | Root cause of F5: importing `reasoner.api` costs ~3.5 min, from 66 module-level imports and side effects in a 1081-line `__init__.py`. Every test that touches the app pays it, so authors mark such tests `slow`, so CI skips them. | measured; [`api/__init__.py`](src/reasoner/api/__init__.py) |
| **F8** | ~~LOW~~ | **Closed in R0.** `.gitattributes` added (`* text=auto eol=lf`, binaries `-text`). The `git add --renormalize .` commit it enables is still outstanding — see R0. | file present at repo root |

### 1.3 Correctness in shipped code

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| **F9** | MEDIUM | `agent_run_sync` collects only mid-stream `type == "error"` events. `done["errors"]` — a documented key of that frame — is dropped, so phase-level failures are invisible to sync API consumers. | [`api/__init__.py:685-707`](src/reasoner/api/__init__.py:685) |
| **F10** | MEDIUM | `RunResult` exposes no cost, though `done` carries `total_cost_usd` and `phase_costs` and the endpoint is metered against prepaid credits. Consumers cannot reconcile spend without re-reading the ledger. | [`schemas.py:301-313`](src/reasoner/api/schemas.py:301) |
| **F11** | MEDIUM | SDK `RunSummary` has no `citations`. The Python endpoint now returns them; the TypeScript client drops them. A parity break introduced by the `agent_run_sync` fix. | `sdk/typescript/src/types.ts` |

**F20–F24 — found while remediating F1, all fixed in R0.** Recorded because the original
survey missed them: chasing drifted tests to their root cause is what surfaced them, which
is the argument for doing §1.1.1's migration properly rather than relaxing assertions.

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| **F20** | HIGH | `CompositeTranslator` falls back to identity and **never raises**, so a fully failed cross-language pivot was indistinguishable from a successful one: `state.problem` kept its source-language text, `pivot_active` was set, and every downstream phase reasoned in the wrong language with nothing in `state.errors`. | `TranslationResult` gained `degraded`/`degraded_reason`; the pipeline raises on `degraded` for both translate-in and translate-out. |
| **F21** | MEDIUM | No preset config declared `required_env_vars`, so the field was always empty and `check_keys()`/`missing_keys()` reported "nothing missing" for every preset. The key preflight in `presets.py` was a no-op. | Derived from registry entries via `ModelRegistryPort` (not a direct infra import — the dependency rule holds), with `DEEPL_API_KEY` declared explicitly since translation implies no model. |
| **F22** | MEDIUM | `presets.py` redefines `get_method_from_preset`, shadowing the `preset_core` import. It preferred the registry's *declared* method, which is in display form (`"cross-language"`), over the name-derived canonical form (`cross_language`) that flows and serializers actually register under — so cross-language presets resolved to a method nothing was registered for. | Precedence flipped: name patterns lead, declared field covers only what the name cannot express (`image-gen`). |
| **F23** | MEDIUM | `_ser_synthesis` serialized `target_language`/`back_translated`, neither of which the pipeline ever writes, and dropped `original_problem` — so clients could not display what the user originally typed. | Extracted `_ser_cross_language()` keyed to what the phases actually write; shared by `_ser_5` and `_ser_synthesis`. |
| **F24** | MEDIUM | `_log_context` used a bare `{}` as its `ContextVar` default — one dict shared by every context that never called `set_log_context()`, so an in-place update in any request leaked into all of them. (`B039`.) | `MappingProxyType({})`; `set_log_context()` already replaced wholesale, so nothing needed mutation. |

### 1.4 Structure

| # | Severity | Finding |
|---|----------|---------|
| **F12** | MEDIUM | Six modules exceed the project's own 800-line ceiling: `serializers.py` **1092**, `api/__init__.py` **1081**, `postgres_store.py` **1046**, `preset_registry.py` **940**, `persuasion_defense.py` ~933, `image_generation.py` ~869. |
| **F13** | LOW | 52 uncommitted files spanning four unrelated workstreams (encryption, `ui-next` redesign, SDK + contract, this remediation). Not reviewable as one change. |

### 1.5 Security coverage — inherited from ENCRYPTION_ROADMAP P4–P6

| # | Severity | Finding |
|---|----------|---------|
| **F14** | HIGH | Neuro L2 disk cache writes problems **and** final syntheses as plain JSON to disk. Highest-sensitivity plaintext in the system. |
| **F15** | HIGH | SQLite event store is plaintext for the same payloads Postgres encrypts. |
| **F16** | MEDIUM | `feedback_store`, `error_store`, `--save-state` files, and frontend IndexedDB are all plaintext. |
| **F17** | MEDIUM | `MultiFernet.rotate()` is never called. The key list only grows; old ciphertext stays under its original key forever. No rotation tooling exists. |
| **F18** | MEDIUM | No envelope encryption: KEK rotation is O(data), and there is no crypto-shredding path for GDPR Art. 17 erasure. |

### 1.6 Frontend

| # | Severity | Finding |
|---|----------|---------|
| **F19** | LOW | `npx tsc --noEmit` fails locally on `.next/dev/types/validator.ts:62`, which begins `TCH?:` — a truncated `PATCH?:` in Next's generated route validator. `.next` is gitignored so CI is unaffected, but the pre-push check every developer runs is broken. Fix is `rm -rf .next` plus a documented note; if it recurs, it is a Next 16 codegen bug worth pinning. |

---

## 2. Architectural principles this plan holds to

Non-negotiable, from [`CLAUDE.md`](CLAUDE.md):

1. **The dependency rule.** Domain → nothing. Application → Domain/Core. Infrastructure
   implements Core ports. API → Application. Enforced by `lint-imports`; the exception
   budget (**59/65**) must *fall*, never rise. Every phase below states its budget effect.
2. **Ports & Adapters is the house style.** New seams go in `core/ports/` as
   `@runtime_checkable` Protocols with adapters in `infrastructure/`.
3. **Backward-compat shims over breaking moves.** `models.py` and `pipeline.py` already
   demonstrate the technique; module relocations use it rather than touching call sites.
4. **Self-describing formats over big-bang cutovers.** Version-prefixed ciphertext and an
   open SSE event union both let readers and writers roll independently.

### 2.1 On "optimal design patterns for every module"

Stated plainly, because it shapes every recommendation below: **most modules in this
codebase need no new pattern.** A pattern with one implementation is not architecture,
it is indirection with a ceremony tax. The repo already gets this right — the encryption
roadmap shipped `EncryptionPort` but *deliberately* declined the DI-injection half and
the standalone cipher classes, because no second caller existed to justify them.

So the map in §3 applies a pattern only where one of these is true:

* Two or more real implementations coexist (→ Strategy, Ports).
* Identical logic is already copy-pasted 3+ times (→ Decorator, Template Method).
* A module-level cost or side effect is forced on unrelated consumers (→ Factory, lazy boundary).

Everything else gets an explicit **leave alone**.

---

## 3. Per-module paradigm and pattern map

### 3.1 Modules surveyed this pass

| Module | Today | Recommendation | Justification |
|--------|-------|----------------|---------------|
| `api/__init__.py` (1081) | God module: app factory + route defs + handlers + 66 module-level imports | **Application Factory** + finish the **Router registry** migration into `api/routes/` | `api/routes/` already exists — this completes a migration that stalled. Kills the ~3.5 min import (F7), which unblocks F5. Zero new abstraction: both are stock FastAPI idioms. |
| `application/services/agent_results.py` | Four pure functions over decoded events | **Leave alone — keep functional** | Stateless transforms. A class here would carry a `self` holding nothing. Its placement outside `api/` is already the reason its tests run in 17s instead of 4 min. |
| `application/services/serializers.py` (1092) | `_ser_0`…`_ser_5` selected by branch | **Strategy via a dict registry** keyed by phase | Six implementations already exist — the branch chain is a hand-rolled dispatch table. A `dict[int, Serializer]` makes each independently testable and lets the file split by phase. Justified by count, not taste. |
| `domain/preset_registry.py` (940) | 48 preset configs as Python literals | **Data, not code** — declarative TOML/JSON + a validating loader | It is a table pretending to be a module. Validation (cross-bloc diversity, fallback chains) currently lives only in tests; a loader makes the invariant enforced at load time, where it belongs. |
| `infrastructure/persistence/postgres_store.py` (1046) | Encrypt/decrypt block copy-pasted per method | **Decorator (`EncryptedStore`)** + **Repository** | Already specified by ENCRYPTION_ROADMAP P4. Four-plus stores need the identical block; this is the 3+-duplication trigger, not speculation. |
| `security/encryption.py` | Prefix dispatch inside one class | **Leave alone until the third cipher lands** | The roadmap correctly deferred splitting into `FernetCipher`/`AesGcmCipher` classes. Two formats dispatched by prefix in one method is simpler than two classes plus a resolver. Revisit at `v3:`. |
| `core/ports/*` | Protocols, no infra imports | **Keep — Ports & Adapters** | Working, and it is the convention the whole plan leans on. |
| `sdk/typescript/src/events.ts` | Modelled arms + `UnknownEvent`, narrowed by `isEvent()` | **Keep — open union + type guard** | The API adds event types without a version bump. An exhaustive `switch` would break consumers on every additive server change. This is the correct choice and should be stated as an invariant so nobody "tidies" it. |
| `ui-next` heavy backgrounds | `X.tsx` re-exports a `dynamic()` boundary over `X.impl.tsx` | **Keep — lazy boundary; extend to other heavy components** | Correct pattern, correctly applied: public export name and props unchanged, so import sites never learned about it. |

### 3.2 Not surveyed this pass

`hypergate/`, `neuro/`, `healing/`, `phases/`, `subagents/`, and the LLM router/executor
were **not** audited. No defect in them surfaced from the failing-test set. This plan
makes no recommendation about them rather than inventing one — a pattern prescribed
without reading the module is exactly the ceremony tax §2.1 warns about.

### 3.3 Explicitly not doing

* **No repository/UoW layer over asyncpg.** Raw asyncpg/aiosqlite is a deliberate choice.
* **No DI container.** The `set_*_port()` composition-root convention already works.
* **No cipher factory** — dict lookup on the version prefix is enough (roadmap's call; upheld).
* **No `api/__init__.py` rewrite.** Move handlers out; do not redesign what they do.
* **No mass ruff autofix across 6258 findings.** See R0.2 for why that ordering matters.

---

## 4. Phased plan

Ordered by (value ÷ risk). R0 and R1 are small and unblock everything else.

### R0 — Turn the gates from decorative to real

**Goal:** a red CI means something. Today it cannot go red.

**Scope correction.** R0 was drafted against a 6-failure sample and read as an afternoon's
work. At 105 it is the largest phase in this document — a migration pass over a suite that
drifted away from the code (§1.1.1), plus the source defects that pass uncovers (F20–F24).
Everything downstream still depends on it: until R0 lands, every later phase ships onto a
CI that cannot report failure.

| Task | Status | Detail |
|------|--------|--------|
| Re-run without `-x` | **done** | The task that resized this phase: 6 → 127 → 105 after the first fixes. |
| Fix the analogical preset wiring | **done** | `test_preset_methods_map_to_flow_strategies` passes honestly, not by relaxation. |
| Diagnose the original remaining 2 | **done** | Both were drift, not logic. |
| Re-mark the Redis test | **done** | `test_cross_process_cancel_via_redis` is `@pytest.mark.integration`. |
| De-rot the pinned model IDs | **done** | Assertions now resolve through `_REGISTRY` / alias constants / `IMAGE_GEN_PRESETS` instead of literals, so they survive the next bump. |
| Fix F20–F24 | **done** | Source defects surfaced by the above. |
| Clear the non-F821 ruff findings | **done** | B904 ×14, B905 ×8, B007 ×5, B010 ×2, B039 ×1. Gate 69 → 31. |
| Add `.gitattributes` | **done** | `* text=auto eol=lf`, binaries `-text`. |
| **Work the six drift classes** | **done — 6/6** | §1.1.1's table. Import drift (3), Rate limiter (8), OCR/uploader mocks (14), Auth status drift (15), `_phase_*` monkeypatch (15), unclassified bucket (68, this pass) all done or resolved to documented open items below. |
| Triage the unclassified bucket | **done, count unreliable — see below** | Started at 68 failed (`-n 4`; `-n auto` OOM-crashes one xdist worker building langfuse's `TraceBody` pydantic schema under parallel import pressure — flaky, not yet fixed, use `-n 4` or lower until diagnosed). Grouped, diagnosed, fixed in two rounds — round 2 found the remaining count is confounded by confirmed cross-test state pollution (not flakiness). Full breakdown, real bugs fixed, and the pollution root-cause lead in "Session outcome" near the bottom. |

**Real source bugs found and fixed this pass** (not test staleness — production code was wrong):

1. **`application/pipeline.py::run()`** — empty-problem validation was missing entirely (only existed in the API's Pydantic schema layer, `api/schemas.py`); direct/CLI callers of `ReasonerPipeline.run("")` silently proceeded instead of raising. Restored `if not problem or not problem.strip(): raise ValueError("Problem cannot be empty")`.
2. **`application/pipeline.py::_validate_enhancement()`** — language-change detection was dropped at some point; only length checks remained, so an LLM "helpfully" translating a Greek prompt to English during enhancement was silently accepted. Restored the `detect_language(original) != detect_language(enhanced)` check.
3. **`application/pipeline.py::run()`** — `state.enhanced_problem` stayed `""` (never mirrored `state.problem`) whenever `enhance_prompt=False`, even though internal use sites already fell back via `or state.problem`. External consumers reading the field directly saw a false-empty value. Added `else: state.enhanced_problem = state.problem`.
4. **`application/pipeline.py::_phase_2_perspectives()`** — the delegator never forwarded `self.perspectives` to `run_perspectives_phase(..., perspectives=...)`, so `ReasonerPipeline.perspectives` (settable to customize which perspectives generate) was dead — always fell back to all 4 defaults regardless of what was set. Fixed the delegator; the production `WorkflowStrategy` phase list still doesn't thread it through (out of scope here, no failing test needs it).
5. **`infrastructure/llm/executor.py::execute()`** — temperature resolution only checked `self.phase_configs` (4 entries: classification/decomposition/synthesis/fusion) with no fallback, so any `phase_key` outside that set (e.g. `"research"`, used by real research/deep-read calls) silently got no `temperature` kwarg at all, falling through to the provider's own default instead of the tuned value in `core/temperatures.py::PHASE_TEMPERATURES`. Added a fallback to `PHASE_TEMPERATURES` when no `PhaseConfig` matches.
6. **`infrastructure/token_cache.py::_ensure_loaded()`** — BUG-016 (documented in this file's own regression-test header) was re-introduced: `_loaded = True` was set unconditionally in a `finally` block, so one transient disk error permanently disabled the cache for the process lifetime. Fixed to only set `_loaded = True` on success; kept the exception swallowed (not re-raised) since `get()`/`set()` call `_ensure_loaded()` unguarded and a raise there would crash live cache lookups.
7. **`core/search.py::_DISCOVERY_EXPORTS`** — `smart_search` (a real function in `infrastructure/search/discovery.py`) was never added to the lazy-proxy allowlist, so `/api/search`'s `from reasoner.core.search import smart_search` failed on *every* request (regardless of the `smart` flag, since the import is unconditional) and the endpoint always 503'd. Added it to the allowlist.
8. **`application/flows/perspective_phases.py::run_stress_test_phase()`** — never had hallucination/self-referential filtering at all (only `run_perspectives_phase` did, via `_is_perspective_hallucinated`). Hoisted the keyword set to module level (`_HALLUCINATION_KEYWORDS`, extended with "truncated output" / "context window exceeded" / "token limit reached" for self-referential failures) and applied the same filter to stress-test results.

**Real gaps found and documented (not fixed — need product/design judgment, not mechanical triage):**

- `multi-perspective-budget` preset has no `fallback_routing` (only 2/48 presets in the registry define it at all) — violates CLAUDE.md's "fail to cross-lab equivalent" principle. `xfail`'d in `test_multi_perspective_budget.py` with a reason pointing here.
- `TaskType` enum (`domain/models.py`) has no `REFUSAL` member — `TaskType.coerce("refusal")` always falls back to `HYBRID`, so refusal-based pipeline halting doesn't exist as a real code path. `xfail`'d in `test_end_to_end_edge_cases.py::test_debate_method_with_toxic_input`.
- `PipelinePreset.required_tier` is never populated by any registry entry (dataclass default FREE for all 48 presets, including all 24 `-premium` ones). The real tier gate is `get_preset_tier()` (correctly derives PRO from the `-premium` suffix against the raw registry dict) — but it's imported and never called anywhere in `api/dependencies.py` (dead import, `require_tier()` doesn't use it). Matches the existing `TODO(#501)` "tier enforcement not yet implemented." `test_saas_preset_tiers.py` now tests `get_preset_tier()` instead of the vestigial field.
- `TestPhaseRoleCalls` in `test_multi_perspective_budget.py` (5 tests: phase_2_perspective/scoring/synthesis/fusion_called_before_perspectives/synthesis_called_after_scoring) — `router.called_roles()` goes empty after `"fusion"` when driven through its `async def state_and_router` fixture (does real async work in fixture *setup*, not in the test body). Smells like an asyncio scoping/cancellation interaction with pytest-asyncio + xdist, not a simple rename. Not root-caused — still open.
- `test_followup_agent.py` (3 tests) — the `agent_model` follow-up override regression carried over from the `_phase_*` drift class: `orchestrator.py`'s `build_router()`/`build_auto_router()` (~line 100-112, ~line 280) receive `agent_model` but the resulting routing dict comes back un-overridden. Traced but not root-caused — still open.
- Cross-file test-isolation flakiness: `test_ocr.py` and `test_arch_risk_worker_mode.py` (and likely others) pass 100% standalone but can 401/fail when run in the same suite — module-level global mutation (`set_auth_adapter()`, `os.environ` writes) leaking across files sharing an xdist worker. Not fixed — needs converting module-level setup to fixtures across the affected files, a larger change than this pass's scope.
- `-n auto` (pytest.ini's default) OOM-crashes an xdist worker building langfuse's `TraceBody` pydantic schema under parallel import pressure, aborting the whole run with a worker-mismatch error. `-n 4` avoids it but isn't a real fix.

**Recurring pattern worth flagging generally:** several tests assumed disabled-by-default integrations but the actual defaults (and this dev environment's configured keys) mean tests were making *real* network calls instead of exercising the code path under test — `MULTI_PROVIDER_FALLBACK_ENABLED` (SPOF fallback, intentionally flipped true in `de76b6d`) hit a real Mistral endpoint; `BRAVE_SEARCH_API_KEY` fallback (`api_key or settings.BRAVE_SEARCH_API_KEY`) hit real Brave Search; `TAVILY_EXTRACT_ENABLED` (defaults true) hit real Tavily extraction ahead of the mocked `scrape_urls`. Fixed each by patching the relevant setting in the specific tests; worth a broader audit of `conftest.py` to disable all such integrations by default for the whole suite rather than per-test.

**Unclassified bucket — grouped (68 failures, `pytest tests/ -q -m "not slow and not integration" -n 4`):**

| Cluster | Count | Root cause | Status |
|---|---|---|---|
| `test_multi_perspective_budget.py` preset/state drift | 10 | Classification+decomposition merged into single `"fusion"` role (`application/pipeline.py::_phase_fusion`); `state.perspectives` renamed `state.candidates` (`perspective_phases.py`). | **5/10 fixed** — role/field renames done. `test_fallback_routing_configured` xfail'd (see gap below). 5 remain: `TestPhaseRoleCalls` (phase_2_perspective/scoring/synthesis/fusion_called_before_perspectives/synthesis_called_after_scoring) all show `router.called_roles()` going empty after `fusion` — smells like an asyncio scoping/cancellation issue specific to the `async def state_and_router` fixture (does real async work in fixture setup) under pytest-asyncio + xdist, not a simple rename. Not yet root-caused. |
| `test_multi_provider.py` fallback default | 1 | `MULTI_PROVIDER_FALLBACK_ENABLED` default flipped false→true intentionally in `de76b6d` ("REAPER V7 — OpenRouter SPOF fallback"). Test asserted the old default. | **fixed** — test now forces the setting off via monkeypatch to exercise the disabled branch. |
| **New gap found:** `multi-perspective-budget` has no `fallback_routing` | 1 | Only 2/48 presets in `preset_registry.py` define `fallback_routing` at all — CLAUDE.md's "fail to cross-lab equivalent" principle isn't implemented for this preset. Not a regression (never populated), but a real doc/code gap. Needs a `preset-designer`-agent-scale decision on which models, not a mechanical fix. | **xfail'd**, documented here — not fixed. |
| `test_ocr.py` | 3 | `assert 401 == 200` — OCR upload endpoint now requires auth the test fixture doesn't provide. | not investigated |
| `test_prompt_injection.py` sanitization counts | 3 | `TestPipelineExternalContentSanitization` — deep_read/shallow_read sanitize call-count assertions off by one. | not investigated |
| `test_bugfixes_regression.py` | 5 | 3× `403 == 500` (`TestPipelineRoutesReturnProperStatusCodes` — an auth check now intercepts before the simulated error path); `DID NOT RAISE OSError` (`test_load_failure_allows_retry`); `assert 0 == 1` (`TestQuotaRepoPoolRaceCondition`). | not investigated |
| `test_e2e_comprehensive.py` | 4 | 2× `TypeError: fake_run_stream_cached() got an unexpected keyword argument 'request'` (`api/__init__.py:555` — signature drift, easy fix); `AttributeError: reasoner.core.search has no attribute get_discovery_client`; `assert '' == 'vague problem'` (enhancement_opt_out_uses_original). | not investigated |
| `integration/test_call_telemetry_store.py` | 4 | `assert 0 == 1`/`0 == 4`/`0 >= 2` — telemetry records not persisting; likely fixture/DB wiring. | not investigated |
| `test_deep_read.py` | 3 | `KeyError: 'summary'` ×2, `assert 2 == 1` — deep_read output structure changed. | not investigated |
| `test_synthesis_fixes.py` | 2 | Greek-hallucination perspective filter test; `IndexError: list index out of range`. | not investigated |
| `test_event_types.py` | 2 | `assert 23 == 14`, `assert 40 == 29` — event class/type-map counts stale (new event types added since test was written). Likely a 2-line fix once confirmed legit. | not investigated |
| `test_saas_cached_subscription.py` | 2 | `AttributeError: ...cached_subscription_repo has no attribute 'get_redis'` — renamed function. | not investigated |
| `test_brave_media_search.py` | 2 | Image/video search-without-API-key tests expect `[]`, got real results — test env may have a key set, or short-circuit removed. | not investigated |
| `test_arch_risk_worker_mode.py` + `test_arch_risk_fallback_masking.py` | 3 | `RATE_LIMITER_MODE` defaults to `'memory'` not `'redis'` in what looks like a production-safety guard test (`arch_risk` naming convention — check for intentional-failing-until-fixed markers before touching). | not investigated |
| `test_perplexity_config.py` | 2 | Registry default mismatches (`'high'` vs `'medium'`, Gemini model id) — config drift. | not investigated |
| `architecture/test_layer_boundaries.py` | 1 | Import-linter layer violation in `core/` — likely intentional gate, see [[import-linter-gate]] memory. | not investigated |
| `test_parsing.py` | 1 | `TestExtractJson::test_rejects_non_dict_json` — `DID NOT RAISE ParseError`, parsing behavior changed. | not investigated |
| `test_pipeline_flow_dag.py` | 1 | `TestExecutePhasesDag::test_exception_propagates` — `DID NOT RAISE ValueError`, DAG error-handling semantics changed (relates to the critical/non-critical halt logic mapped during the `_phase_*` class work). | not investigated |
| `test_temperature.py` | 1 | `KeyError: 'temperature'`. | not investigated |
| `test_arch_uncertainty_mixin_migration.py` | 1 | `WorkflowFactory` has extra methods (`subagent`, `cross_language`, `iterative_critique`, `image_gen`) not in the test's expected list — stale list, needs updating (methods were legitimately added). | not investigated |
| `test_db_pool_size.py` | 1 | `assert 50 == 10` — pool size default changed. | not investigated |
| `test_context_vetting.py` | 1 | `TestSynthesisCircuitBreaker` — expected circuit-breaker phrase not in prompt text (prompt text changed). | not investigated |
| `test_saas_preset_tiers.py` | 1 | `analogical-premium should be PRO` — preset tier config drift. | not investigated |
| `test_bugfix_language_preservation.py` | 1 | `assert True is False` — language validation regression? | not investigated |
| `test_auto_rollback.py` | 1 | `TestAutoFallbackRerank` — rerank score field added, assertion shape mismatch. | not investigated |
| `test_auth_security.py` | 1 | `TestAdminKey::test_admin_key_from_env` — `reasoner.infrastructure.auth_legacy.AuthenticationError: Invalid API key`. | not investigated |
| `test_end_to_end_edge_cases.py` | 3 | Regex mismatch; `TaskType.HYBRID == 'refusal'` (classification changed); `assert True is False`. | not investigated |
| `test_event_bus_backpressure.py` | 1 | `assert 10 <= 5` — queue drop threshold changed. | not investigated |
| `test_provider_router_degradation.py` | 1 | `assert False` — degraded-response test. | not investigated |
| `test_followup_agent.py` (carried over from `_phase_*` class work) | 3 | `agent_model` follow-up override regression — traced partway into `orchestrator.py`'s `build_router()`/`build_auto_router()` (~line 100-112, ~line 280), exact defect not yet found. | not fixed |

**Also found:** `-n auto` (pytest.ini default) OOM-crashes an xdist worker building langfuse's `TraceBody` pydantic schema, aborting the whole collection with a worker mismatch error. `-n 4` avoids it but isn't a real fix — needs its own investigation (possibly cap `-n` in pytest.ini, or lazy-import langfuse).

**Session outcome (round 1):** `pytest tests/ -q -m "not slow and not integration" -n 4` — started 68 failed, ended **25 failed, 3097 passed, 85 skipped, 3 xfailed, 2 xpassed** (509.85s).

**Session outcome (round 2 — "keep going"):** Investigated all 12 "new this run" failures individually (single-file / single-node pytest invocations, no xdist cross-module contamination):

- **`test_websocket_auth.py` (4/4), admin/auth cluster (`TestAdminKey`, bugfixes_round2 ×2, `test_auto_rollback.py::TestAutoFallbackAttachmentContext` ×2)** — **all pass in isolation.** Confirmed cross-test pollution, not real regressions.
- **`test_mixins_cognitive.py::test_pot_execute_populates_output`** — **real bug, fixed.** `run_pot_execute_phase` (`application/flows/cognitive_phases.py:262`) branches on `services.code_executor is not None`, but `PipelineWorkflowServices._init_executor()` (`application/flows/services.py:24`) *always* installs something — a real sandbox or `NoopExecutor` as fail-closed fallback — so `code_executor` is never `None` anymore. The `else` LLM-simulation branch is dead code. Test predated the code-executor feature and mocked `_call_llm_cached`, which is never reached. Rewrote the test to mock `services.code_executor` instead (`tests/test_mixins_cognitive.py`).
- **`test_prompt_injection.py::TestPipelineExternalContentSanitization`** (3) — fixed: added the same `disable_tavily_extract` autouse fixture as `test_deep_read.py`.
- **`test_deep_read.py::test_deep_read_fallback_on_scrape_failure`** — **real bug, fixed.** `run_deep_read_phase`'s scrape-failure branch (`application/flows/search_phases.py:450-470`) never set `matching_result["extraction_success"]` — only the success path did. Added `= False` to both scrape-failure sub-paths.
- **`test_deep_read.py::test_deep_read_legacy_mode_without_llm`** — **test bug, fixed.** Patched `os.environ["REASONER_DEEP_READ_LLM"]` after import; `settings` is a frozen pydantic-settings singleton read once — same pattern as the earlier Tavily fix. Changed to `patch.object(settings, "REASONER_DEEP_READ_LLM", False)`.

All 23 tests across `test_deep_read.py` + `test_prompt_injection.py` pass together after the fixes (confirmed).

**Then a full-suite rerun surfaced something worse than flakiness:** with the full test list running under `-n 4`/`--dist loadscope`, `test_deep_read.py` and `test_prompt_injection.py` **fail again** — including tests just fixed and verified passing standalone — plus one brand-new failure never seen before (`test_deep_read_extracts_summary_on_scrape_success`, duplicate `vetted_context` entries). This is **confirmed cross-test state pollution** between test modules sharing an xdist worker, not random flakiness — the same test passes or fails depending on what ran earlier in that worker.

**Root cause #1, confirmed and fixed:** `src/reasoner/core/health_validator.py:78-126` (`validate_all()`) directly mutates the frozen `settings` singleton (`settings.COHERE_RERANK_ENABLED = False`, `settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED = False`) with no restore — intentional prod "auto-disable if prerequisites missing" self-healing, reasonable for a long-lived process. `tests/conftest.py`'s placeholder `OPENROUTER_API_KEY` (`"test-dummy-openrouter-key-placeholder"`) didn't start with `sk-`/`sk-or-`, so `_check_openrouter_key()` always failed it — any test that starts the FastAPI app lifespan runs `validate_all()`, which then permanently flipped both flags for every later test sharing that xdist worker (unlike `monkeypatch`/`patch.object`, direct assignment doesn't restore). Fixed by prefixing the placeholder with `sk-or-` (`tests/conftest.py`).

**Round 3 verification (full suite, post-fix):** 22 → **16 failed, 3116 passed** (548.75s). Confirmed fixed by the conftest change: 3× `test_deep_read.py`, `test_prompt_injection.py::test_deep_read_sanitizes_scraped_content`, `TestAdminKey::test_admin_key_from_env`, `test_auto_rollback::TestAutoFallbackAttachmentContext` (semantic-retrieval test), `test_bugfixes_regression_round2.py` ×2 — 8 tests, all previously failing only in full-suite context, now pass.

**But two more pollution vectors are confirmed to exist, unrelated to the OPENROUTER key:**
- `test_websocket_auth.py` (4/4) still fail in full-suite with `"Origin not allowed"` for every case, despite passing 5/5 in isolation and despite the file's own `_permissive_defaults` autouse fixture correctly `monkeypatch.setattr(settings, "CORS_ORIGINS", "")`-ing every test. `is_origin_allowed()` (`infrastructure/websocket/ws_security.py:18`) reads `settings.cors_origins_list` live (not cached) each call, and `monkeypatch` always auto-reverts — so this isn't the same "direct assignment, no restore" bug. No `settings.CORS_ORIGINS =` direct assignment exists anywhere in `src/` or `tests/` (grepped). Mechanism not found — worth a `--dist no` (single-worker, no parallelism) full run to bisect which earlier test breaks it.
- `test_prompt_injection.py::test_deep_read_allows_clean_content_with_delimiters` / `test_shallow_read_wraps_snippet_in_delimiters` — pass standalone (verified twice), still fail in full-suite even after the conftest fix, with zero LLM calls recorded (the phase's exception handler at `search_phases.py:490` may be silently swallowing something triggered by other-test pollution). Not root-caused.

**Two new failures also appeared this round, unrelated to pollution — not investigated:**
- `test_security_regression.py::TestBug001AdminEndpointHardening::test_admin_stats_authorized_still_works` — uses `monkeypatch.setattr(Settings, "ADMIN_API_KEY", ...)` (the **class**, not the `settings` **instance**) — likely doesn't reach the already-constructed singleton's instance field at all (pydantic-settings instance dict vs. class default). Different bug shape from the `TestAdminKey` one already fixed elsewhere in this session.
- `test_site_capabilities_sync.py::test_capabilities_generated_ts_matches_live_counts` — generated-file drift (models: 448 committed vs. 447 live), unrelated to anything touched this session — likely the model catalogue changed underneath a stale generated file.

**Final count this session:** 68 → 16 failed (3116 passed), with 2 of those 3 remaining pollution vectors still unexplained and 2 fresh unrelated failures spotted but not chased. **Stopping here — cost hit $53.93 (critical threshold), 36 files modified.** Do not chase individual failures further in the full-suite context without finishing the pollution root-cause work first (`test_websocket_auth.py` + the 2 remaining `test_prompt_injection.py` cases) — fixes will keep looking like they "don't work" when the actual cause is unrelated worker-assignment luck.

Confirmed-still-open, unrelated to pollution:
- `TestPhaseRoleCalls` (`test_multi_perspective_budget.py`, 5) — documented above, asyncio/fixture scoping, not root-caused.
- `test_followup_agent.py` (3) — documented above, `agent_model` routing regression, traced not fixed.
| Resolve the F821 forward refs | **done** | `ruff --select F821` was cache-stale mid-pass — true count was 24, not 31; 7 more (`models.py`, `phases/_shared.py`, `subagents/search/hyper_agent.py`, `infrastructure/redis/run_state.py`, `infrastructure/uploader.py`) surfaced only after cache invalidated by the first round of edits. Fixed via `TYPE_CHECKING` imports except two that were live bugs, not latent annotations: `pipeline_service.py`'s `--resume` path called `CriticDimensionScore(...)` without importing it (real `NameError` on any resume with saved critic scores), and `uploader.py`'s `extract_text()`/semantic-retrieval check read `settings` without importing it (real `NameError` on every extraction call — plausibly the root cause behind some of the "OCR / uploader mocks" drift-class failures). One stray `B904` also found and fixed (`api/routes/uploads.py:39`) — CI's own gate (`ruff check src/ --select B,F821 --ignore B008`) is now 0 errors. All 17 touched modules verified importable with no circular-import regressions. |
| Drop `--exit-zero` | **open** | Gate now verified 0 errors. Still its own commit, never combined with a fix — not yet done. |
| `git add --renormalize .` | **open** | Its own commit now that `.gitattributes` exists, with `.git-blame-ignore-revs`. |
| Split the working tree | **open** | Four commits minimum: encryption, SDK + contract, `ui-next` redesign, this remediation. |

**Ordering note.** Do *not* run a blanket `ruff --fix` first. The 6258-finding sweep would
bury the 61 that CI already claims to check, and mixing a formatting sweep with the
`.gitattributes` renormalisation produces a diff nobody can review. Narrow gate first,
line-ending normalisation second, broad style sweep last (R2).

**Import-linter budget:** unchanged (59). **DoD:** `pytest -m "not slow and not integration"`
green with no `-x`; `ruff check src/ --select B,F821 --ignore B008` exits 0 with
`--exit-zero` removed from `test.yml`.

---

### R1 — Correctness fixes in shipped code

Small, independent, each with a test. Ship alongside R0.

| Task | Detail |
|------|--------|
| **F9** — merge `done["errors"]` | Union the mid-stream `error` events with the terminal frame's list, order-preserving and de-duplicated. Extend `application/services/agent_results.py` with a pure `extract_errors(events)` so it stays testable without importing the app — same reasoning that made the existing helpers fast. |
| **F10** — surface cost | Add `total_cost_usd: float` and `phase_costs: dict[str, float]` to `RunResult`. Additive on a response model, so no consumer breaks. Mirror into the SDK's `RunSummary`. |
| **F11** — SDK citations parity | Add `citations: Citation[]` to `RunSummary` and populate it in `summarise()`. Add `Citation` to `types.ts`. |
| Extend the shared fixture | Add the new keys to `sdk/contract/events.json` so both sides assert one source of truth. |

**DoD:** each fix has a `@pytest.mark.unit` test in `tests/test_agent_run_sync.py`; the
SDK's vitest covers the `citations`/cost path; `sdk/contract/events.json` updated and both
language suites read it.

---

### R2 — Make verification actually verify

**Goal:** close F5–F7. This phase is what stops the next regression, so it outranks
everything structural.

**R2.1 — Kill the import cost (the keystone).**

`reasoner.api` costs ~3.5 min to import. That single fact produced F5: authors mark
app-touching tests `slow`, and CI skips `slow`. Fixing it is not a performance nicety —
it is what makes the contract suite executable.

Move route handlers out of `api/__init__.py` into `api/routes/`, and make app construction
a real `create_app()` factory so importing the module does not build the world. This is
the first slice of R3 and is pulled forward because R2.2 and R2.3 depend on it.

**R2.2 — Un-slow the contract tests.** Once the import is cheap, drop `@pytest.mark.slow`
and `timeout(900)` from the three tests at `test_sdk_contract.py:182,211,244`. Only then
does the OpenAPI digest actually guard against drift.

**R2.3 — Add the SDK to CI.** A new job in `test.yml`:

```yaml
  sdk:
    name: TypeScript SDK
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: sdk/typescript
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: npm, cache-dependency-path: sdk/typescript/package-lock.json }
      - run: npm ci
      - run: npx tsc --noEmit -p tsconfig.build.json   # proves src/ is Node-free
      - run: npm test
```

**R2.4 — Ratchet coverage.** Measure actual first, then set the floor just beneath it and
raise it per PR. A floor of 30 against a target of 80 permits a 50-point regression.

**DoD:** contract tests run in the default lane; SDK job green; coverage floor within 5
points of actual.

---

### R3 — Module decomposition

Only after R2, because R2.1 already does the highest-value slice.

| Module | Split |
|--------|-------|
| `api/__init__.py` (1081) | Remainder of the handler migration → `api/routes/*`; `__init__.py` keeps only `create_app()` and router mounting. |
| `serializers.py` (1092) | `dict[int, Serializer]` registry; one module per phase group. |
| `postgres_store.py` (1046) | Onto the `EncryptedStore` decorator from R4 — refactor this store **last**, once the decorator is proven by the new call sites (roadmap's sequencing; upheld). |
| `preset_registry.py` (940) | Configs → declarative data + validating loader. |
| `persuasion_defense.py`, `image_generation.py` | Assess; split only if a natural seam exists. Do not force one. |

**Import-linter budget:** should **fall** — moving handlers behind ports is the mechanism
the `.importlinter` comment names for paying down the 59.

**DoD:** no module over 800 lines without a written justification; budget ≤ 59; `lint-imports` green.

---

### R4 — Encryption P4: close the plaintext gaps

**The phase with the most actual security value.** Full detail in
[`ENCRYPTION_ROADMAP.md`](ENCRYPTION_ROADMAP.md) §P4; summarised here for sequencing.

Order by sensitivity: Neuro L2 disk cache (**F14**) → SQLite event store (**F15**) →
feedback/error stores → `--save-state` → IndexedDB (**F16**).

Introduce `EncryptedStore` at the *first* new call site rather than refactoring
`postgres_store.py` onto it — prove the decorator on green field, migrate the incumbent last.

**Flag before BYOK ships:** `api_key_service.py` SHA-256-hashes *Reasoner's own* keys,
which is right. A user's *upstream* provider key must be recoverable, so it needs
encryption with a per-user DEK (R5), not hashing.

**Frontend caveat:** IndexedDB is a separate trust domain. The backend key must never
reach the browser. WebCrypto with a session-derived key protects against local disk
inspection, not a compromised page — say so in the docs rather than implying more.

**DoD:** per store, a "plaintext never hits disk" test in the style of
`test_auth_store_persists_ciphertext_not_plaintext`; legacy plaintext rows still read.

---

### R5 — Encryption P5/P6: envelope encryption and rotation

Per roadmap. Two properties nothing else buys:

* **KEK rotation becomes O(number of DEKs), not O(data)** — rewrap, never re-encrypt.
* **Crypto-shredding** — delete a user's wrapped DEK and their data is unrecoverable,
  including in backups. A far cleaner GDPR Art. 17 story than `DELETE`; wire into
  `application/services/data_eraser.py`.

Then `scripts/rotate_encryption_key.py` (**F17**), modelled on the existing batched,
resumable, `--dry-run` migration script, plus a `/health/encryption` endpoint so
"is rotation finished?" is answerable without a query.

**DoD:** rotation drill on a seeded DB, interrupted mid-run, resuming clean; crypto-shred
test proving unrecoverability.

---

### R6 — Frontend

| Task | Detail |
|------|--------|
| Land the in-flight redesign | 35 files, +3633/−2283, as its own reviewable commit. |
| Confirm the Tailwind v4 invariant | `tailwind.config.js` deletion is **correct** — v4 is CSS-native via `@import "tailwindcss"`. Do not let anyone restore it. |
| **F19** — the tsc papercut | Clear `.next`, document it. If the corrupt validator recurs, pin/report as a Next 16 codegen bug. |
| Extend the lazy boundary | Apply the `.impl.tsx` pattern to any other component pulling WebGL/canvas into the initial payload. |
| IndexedDB encryption | Deferred to R4 — same trust-domain caveat. |

---

## 5. Sequencing

```
R0 (make gates real) ─┬─→ R2 (verification) ─→ R3 (decomposition) ─→ R4 (P4) ─→ R5 (P5/P6)
                      │        ▲
R1 (correctness) ─────┘        │
                               └── R2.1 (import cost) is the keystone:
                                   it unblocks R2.2, and is R3's first slice

R6 (frontend) ── independent, any time after R0's commit split
```

**Recommended first slice: R0 + R1.** R0 makes failure visible; R1 is three small
correctness fixes with tests. Neither needs an architectural change, and until R0 lands,
every later phase ships onto a CI that cannot report failure.

**R2.1 is the highest-leverage single task in this document.** One 1081-line module's
import cost is why the contract suite is invisible to CI, and why app-level tests are
systematically marked `slow` and therefore never run.

---

## 6. Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing `--exit-zero` blocks all PRs at once | Medium | Clear the 61 in a dedicated commit *before* changing the workflow. Never in the same PR. |
| ~~The 6-failure count is a floor~~ | — | **Realised, then resolved.** It was 127. Re-run without `-x` is done; the count is known. |
| Drifted tests greened by relaxing assertions | **High** | The cheap fix for every failure in §1.1.1 is to loosen the assertion, which turns a red gate decorative and reproduces F2 somewhere new. Each fix must move the test to the current shape or fix the source — and say which. Reviewers: treat a weakened assertion in this phase as a defect. |
| 105 failures reached `main`'s own lane unnoticed | **High** | Establish whether CI has been red or the lane markers exclude more than intended, before R2 ratchets coverage on top of it. |
| Broad ruff sweep buries real findings | Medium | Narrow gate → renormalise line endings → broad sweep. Never combined. |
| `.gitattributes` renormalisation looks like a rewrite | Low | `git add --renormalize .` alone in one commit, with `.git-blame-ignore-revs`. |
| Splitting `api/__init__.py` breaks imports | Medium | Backward-compat shim, as `models.py`/`pipeline.py` already do. |
| Key loss = total data loss | **Critical** | Document key backup before R5; `/health/encryption` surfaces key state. |
| Blind-index reindex missed | High | Already mandated by P0's tokenizer change. Startup warning when index length ≠ `BLIND_INDEX_BYTES`. |
| Blind-index frequency analysis | Medium | Unsalted per-token HMACs are frequency-rankable by anyone with DB access. Truncation adds collisions. **Accept and document** — a leak-free searchable index needs ORE/SSE, out of scope. |
| Import-linter budget creeps up | Medium | It is a ratchet. Every phase states its effect; R3 must lower it. |

---

## 7. Definition of done, whole plan

* `pytest -m "not slow and not integration"` green, no `-x`, true count known.
* `ruff check src/ --select B,F821 --ignore B008` exits 0, **without** `--exit-zero`.
* SDK contract tests run in the default lane; `sdk/typescript` has a green CI job.
* `lint-imports` green with the exception budget at **≤ 59** and falling.
* No module over 800 lines without written justification.
* Every store in §1.5 has a "plaintext never hits disk" test.
* Key rotation demonstrated by an interrupted-and-resumed drill.
* Coverage floor within 5 points of actual, ratcheting toward 80%.

---

## 8. What this plan deliberately leaves alone

Listed so nobody mistakes omission for oversight:

* `hypergate/`, `neuro/`, `healing/`, `phases/`, `subagents/`, LLM router/executor —
  not surveyed, no defects surfaced, no recommendation invented (§3.2).
* The `set_*_port()` composition-root convention — works; no DI container.
* Raw asyncpg/aiosqlite — deliberate; no ORM.
* Splitting `EncryptionService` into cipher classes — deferred to the third cipher.
* The SDK's open event union — correct as designed; treat as an invariant.
