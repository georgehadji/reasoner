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
| Auth status drift | 15 | `assert 401 == 200`, `403 == 500`; the API's auth contract moved under the tests |
| `_phase_*` monkeypatch drift | 15 | Tests patch `ReasonerPipeline._phase_1_decompose` / `._phase_context_vetting`; those are now module-level functions in `application/flows/*_phases.py` |
| Rate limiter refactor | 8 | `_lock_for` and `_sharded` no longer exist; `burst_limit` → `burst_limit_fallback` |
| OCR / uploader mocks | 10 | `patch` targets moved out of `reasoner.uploader` / `reasoner.main` |
| Import drift | 3 | `health_check`, `_CREATIVE_SYSTEM_PROMPT` relocated |
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
| **Work the six drift classes** | **open** | §1.1.1's table. Migrate to the current shapes; do **not** relax assertions to green them. Largest remaining item. |
| Triage the ~54 unclassified | **open** | Group by root cause before fixing, as with the first pass. |
| Resolve the 31 F821 forward refs | **open** | Import under `TYPE_CHECKING`. Latent (F3), but they blind mypy at 31 sites and are a live break waiting for the first one to become a FastAPI dependency. Easy subset: missing `Any` in `infrastructure/llm/base.py` (4) and `subagents/search/hyper_agent.py` (1), `Union` in `phases/_shared.py`, `Path` in `models.py` (2), `httpx`/`AsyncIterator` in `providers/openai_compat.py` (2). |
| Drop `--exit-zero` | **open** | Only after the line above. Its own commit, never combined with a fix. |
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
