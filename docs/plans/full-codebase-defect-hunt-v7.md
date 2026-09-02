# Full-Codebase Defect Hunt (V7) — Plan

**Status:** plan, not executed
**Date:** 2026-09-02
**Protocol:** Autonomous Defect-Hunt Protocol V7 (Proactive). EGFV / RAR / MRADO / PCST
**Predecessor:** `docs/plans/backend-defect-hunt-v7.md` (7 tiers, complete, merged in #43/#44/#45)
**Findings so far:** `docs/reports/defect-hunt-2026-09-01/ROLLUP.md`

Extends the completed backend hunt to everything it deliberately left out. This plan is written against measured counts, not estimates, and it is shaped by four lessons the first hunt actually produced.

---

## 0. What the first hunt taught, and why this plan differs because of it

The backend hunt found 37 confirmed defects across 528 files. Four results from it change how this one should be run.

**An unfaithful test fake is this codebase's most productive defect signature.** Three separate confirmed defects hid behind fixtures that were faithful to nothing: a `str` where asyncpg returns `uuid.UUID` (quota enforcement absent on every PostgreSQL deployment), an async client method stubbed as synchronous (a `TypeError` on the streaming path), and a `_FakeGate` missing an attribute the real object has. In all three, production code matched its test perfectly and the test matched reality not at all. **Section 6 makes fixture fidelity a first-class hunt target, not a side observation.**

**Process-global state leaking between tests is the second signature.** `tests/conftest.py` already documents two instances in its own comments, and this hunt found a third (`_SHARED_CACHE_PORT`, injected by app startup and never released on shutdown). The symptom is always the same: a test that passes alone and fails only under a particular worker split. Any tier touching module-level singletons must hunt this explicitly.

**Ratchets move when a defect hunt succeeds, and they are exact-equality.** The ruff count fell 2249 → 2247 → 2243 then rose to 2244; `api/__init__.py`'s line cap needed 1104 → 1108. Both directions fail the gate. Every tier below states its expected ratchet impact, and the constant is set **once, at the end of a tier**, never mid-run by parallel agents.

**Concurrent agents on one worktree work, but only with disjoint surfaces.** Three tiers ran in parallel successfully when each was given an explicit file boundary and told to record out-of-tier findings as observations. That arrangement is reused here.

---

## 1. Surfaces, measured 2026-09-02

| Surface | Path | Files | Lines | Audited? |
|---|---|---:|---:|---|
| Frontend app | `ui-next/src` | 227 | 29,776 | **Never** |
| Python tests | `tests` | 309 | 51,047 | **Never** (as a subject) |
| Prompt modules | `src/reasoner/phases` | 36 | 4,911 | **Never** (excluded by design) |
| Phase sub-agents | `src/reasoner/subagents` | 30 | 1,986 | **Never** (excluded by design) |
| Ops scripts | `scripts` | 32 | 4,087 | **Never** |
| TypeScript SDK | `sdk/typescript/src` | 7 | 1,652 | **Never** |
| CI workflows | `.github/workflows` | 7 | 1,136 | **Never** |
| DB migrations | `migrations` | 12 | 706 | Partially (one failure found) |
| Backend | `src/reasoner/**` | 528 | 84,988 | Complete, 7 tiers |

**Roughly 89,000 unaudited lines**, slightly more than the backend hunt covered.

---

## 2. A blocking-condition check, resolved before it blocks

V7's Phase 3 requires an **executable** trigger; a candidate with no runnable test stays `[UNK]` and cannot be promoted. So each surface needs a working test runner, or the hunt on it is blocked by the protocol's own rules.

| Surface | Runner | Status |
|---|---|---|
| `ui-next/src` | `vitest` 4.1.4, `@playwright/test` 1.59.1, `@testing-library/react` 16.3.2, `@axe-core/playwright` | Available. 23 existing test files |
| `sdk/typescript/src` | `npm test`, already blocking in CI (`test.yml:175`) | Available |
| `src/reasoner/phases`, `subagents` | pytest | Available |
| `scripts`, `.github/workflows` | none | **Partially blocked. See §5** |
| `migrations` | psql against a container (proven this session) | Available |

**Nothing is fully blocked.** The frontend is the largest unaudited surface and it is fully testable today.

### 2a. A finding that precedes the hunt

`ui-next`'s CI job (`test.yml:118-150`, named "TypeScript type check") runs exactly four steps: `npm ci`, `npx tsc --noEmit`, `npm run lint`, and a design-token grep guard. **It never runs `npm test`.** The `npm test` at `test.yml:175` belongs to the SDK job, which caches `sdk/typescript/package-lock.json` and builds `tsconfig.build.json`.

The only frontend test CI does execute is the Playwright a11y spec in `quality.yml:50`, and that job is `continue-on-error: true`, so it cannot fail the build.

**All 23 vitest files in `ui-next/src` have never run in CI.** [VF]

That is a defect in the verification apparatus, and it changes tier F1's shape: those tests cannot serve as a green baseline, because nobody knows whether they pass. **Running them is step one, before hunting anything.**

---

## 3. Threat model per surface

V7 requires the taxonomy ranked per system. These surfaces have genuinely different risk profiles, and reusing the backend's ranking would misallocate the budget.

**Frontend (`ui-next/src`)** — the user-facing trust boundary and the only surface where a defect is visible to a customer directly.
1. **Trust boundary / XSS** — markdown rendering, `dangerouslySetInnerHTML`, URL handling, the epistemic-mark remark plugin, any user or model text reaching the DOM.
2. **State & effects** — `useEffect` dependency errors, stale closures, missing cleanup (the React analogue of resource lifecycle), race conditions between SSE streaming and component unmount.
3. **Async / streaming** — `usePipelineStream`, WebSocket reconnection, aborted fetches, out-of-order chunk handling.
4. **Persistence** — IndexedDB schema drift, quota exhaustion, migration on version bump.
5. **Type & serialization** — `any` escapes, unvalidated API responses crossing the proxy boundary, optional chaining hiding real absence.
6. **Accessibility as correctness** — focus traps, keyboard reachability. The repo already asserts WCAG 2.2 AA as a floor.

**Tests (`tests/`)** — the subject, not the instrument.
1. **Fixture fidelity** — fakes returning types the real dependency never returns.
2. **Global-state leakage** — module singletons set without teardown.
3. **Vacuous assertions** — tests that cannot fail (assert on a mock's own return, no arrange step, tautological equality).
4. **Order dependence** — tests that pass only in a specific sequence.

**Prompt modules (`phases/`, `subagents/`)** — excluded from the backend hunt because "output quality is not in V7's taxonomy," which remains true. But three classes genuinely are:
1. **Injection surface** — user text interpolated into a prompt without `sanitize_for_prompt()`.
2. **Propagation resistance** — the four documented invariants, particularly Phase-2 generator blindness, which holds *by omission* and can break silently.
3. **Contract** — a prompt promising a JSON shape the parser does not accept.

**Ops (`scripts/`, `.github/workflows/`, `migrations/`)**
1. **Gate correctness** — a gate that cannot fail is worse than no gate. §2a is exactly this.
2. **Migration integrity** — `003_add_indexes.sql` already fails to apply (`ERROR: relation "query_log" does not exist`), so the set cannot rebuild from zero.
3. **Secret handling** in scripts and workflows.

---

## 4. Tiers

Eight tiers. Budgets are sized to the surface, and total 74 candidates, comparable to the backend hunt's 78.

| # | Tier | Surface | Primary classes | Budget |
|---|---|---|---|---|
| F1 | **Frontend trust boundary** | markdown rendering, `lib/security`, proxy routes under `src/app/api/`, any `dangerouslySetInnerHTML` | XSS, injection, unvalidated response | 14 |
| F2 | **Frontend state & effects** | `hooks/`, `stores/app-store.ts`, `usePipelineStream`, WebSocket hooks | stale closure, missing cleanup, unmount race | 12 |
| F3 | **Frontend persistence & types** | `lib/db` (IndexedDB), `lib/types`, `lib/api-client` | schema drift, `any` escape, quota exhaustion | 10 |
| T1 | **Test-suite integrity** | `tests/` (309 files) as subject | fixture fidelity, global leakage, vacuous assertions | 12 |
| P1 | **Prompt injection surface** | `phases/`, `subagents/` | injection, propagation-resistance invariants | 10 |
| O1 | **Gates & CI** | `.github/workflows/`, `scripts/` | gates that cannot fail, secret handling | 8 |
| O2 | **Migrations** | `migrations/`, against a real Postgres | apply-from-zero, ordering, constraint gaps | 4 |
| S1 | **TypeScript SDK** | `sdk/typescript/src` | contract drift vs the backend API | 4 |

**Deliberately still excluded:** generated directories (`graphify-out/`, `.next/`, `node_modules/`, `sdk/typescript/dist/`), and `ui-next/e2e` beyond confirming the a11y spec runs. Recorded as unaudited, not clean.

---

## 5. The partially-blocked surface, stated honestly

`scripts/` and `.github/workflows/` have no test runner, so V7's Phase 3 cannot produce a conventional executable trigger for most candidates there. Two consequences, and neither is "skip it":

- **Gates are testable by falsification.** For a gate, the executable trigger is: introduce a known violation, confirm the gate fails; remove it, confirm the gate passes. A gate that stays green through a deliberate violation is a `[VF]` defect. This is how §2a would be proven, and it is a real, runnable test.
- **Everything else in `scripts/` stays `[UNK]`** unless it is importable and unit-testable. Per protocol, `[UNK]` routes to the runtime-instrumentation list rather than being promoted on reasoning. Expect O1 to produce more `[UNK]` than other tiers. That is the correct outcome, not a failure.

---

## 6. Fixture fidelity as a first-class target (tier T1)

The highest-expected-value tier, because it is the one that makes every other tier's evidence trustworthy.

**Method, mechanical and checkable:**

1. **Type-fidelity sweep.** For each fake standing in for a real dependency, compare the fake's return type against the real one. Known offenders by shape: asyncpg returns `uuid.UUID` for `uuid`, `datetime` for `timestamptz`, `Decimal` for `numeric`; async methods stubbed with `MagicMock` instead of `AsyncMock`. Start from `tests/test_saas_quota_repo.py`, the confirmed case.
2. **Global-teardown sweep.** Find every test that sets a module-level singleton. Any without `try/finally` or fixture teardown is a candidate. `grep` for the known setter family (`set_*_port`, `reset_*`) and check each call site.
3. **Vacuity sweep.** Find assertions that cannot fail: asserting a mock returns what it was configured to return, `assert True`, assertions on unexecuted branches. A test that cannot fail is a coverage lie, and this codebase gates on coverage.
4. **Order-dependence probe.** Run the suite under several worker counts and seeds (`-n 1`, `-n 2`, `-n auto`, `-p no:randomly` on and off). Any test whose result depends on the split is a `[VF]` isolation defect. This is exactly how the `_SHARED_CACHE_PORT` bug surfaced, and it is cheap to automate.

**Deliverable beyond fixes:** a short `tests/README` rule stating fake-fidelity and teardown requirements, so the pattern stops recurring.

---

## 7. Per-tier protocol adaptations

The protocol runs unchanged in structure. Three surface-specific rules matter.

**Frontend triggers must not mock the mechanism under suspicion.** For an XSS candidate, render the real component with `@testing-library/react` and assert on the resulting DOM; do not assert on a sanitizer's return in isolation. For an effect-cleanup candidate, mount and unmount for real and assert the listener or stream is gone. Fake only the network boundary, using MSW or a stubbed `fetch`.

**Accessibility candidates need `@axe-core/playwright`**, already a dependency. A WCAG violation is a `[VF]` defect against a documented repo floor, not a matter of taste.

**Prompt-module triggers assert on the constructed string**, not on model output. "Does user text reach the prompt unsanitized?" is decidable offline and needs no model call. "Is the answer good?" is not in the taxonomy and stays out.

**No live LLM or network calls in any tier.** Same rule that held for all seven backend tiers.

---

## 8. Sequencing

| Step | Tier | Rationale | Parallel? |
|---|---|---|---|
| 1 | **§2a fix + T1** | Make the instruments trustworthy before measuring with them. Wire `ui-next` tests into CI, see whether the 23 files even pass, then hunt the test suite itself | No, do first |
| 2 | **F1** | Largest surface, highest user-visible severity, security-sensitive | Alone |
| 3 | **F2 + F3** | Disjoint from each other | Yes, 2 agents |
| 4 | **P1 + O2** | Disjoint (`phases/` vs `migrations/`); O2 needs the Postgres container | Yes, 2 agents |
| 5 | **O1 + S1** | Disjoint | Yes, 2 agents |
| 6 | **Rollup** | Merge coverage statements into the existing register | No |

**Never more than two concurrent agents.** Three plus a test run exhausted memory this session and crashed `import-linter`, and that cost real time to diagnose.

**One PR per tier.** Never one large PR: the backend hunt stayed reviewable because each tier committed separately with its own evidence.

---

## 9. Verification, per PR

Backend gates still apply to any PR touching `src/reasoner/**`:

```bash
python -m pytest tests/ -q -p no:randomly -m "not slow and not integration"
python scripts/ruff_ratchet.py --max <current>
PYTHONPATH=src lint-imports --no-cache --verbose
python scripts/count_importlinter_exceptions.py --max 60
```

Frontend PRs additionally:

```bash
cd ui-next && npx tsc --noEmit && npm run lint && npm test
```

Current baselines, verified 2026-09-02:

```
3994 passed, 83 skipped, 4 xfailed          (backend)
PASS: 2244 violations matches ratchet MAX=2244
Contracts: 1 kept, 0 broken
PASS: 60 exceptions matches ratchet MAX=60
api/__init__.py line cap: 1108
```

`ui-next` has **no established baseline**, by §2a. Establishing one is step 1.

**Per fix, the protocol's bar, unchanged:** a proof-of-defect test that fails without the fix and passes with it, at least two boundary tests, one no-regression test. A fix whose test was never seen to fail beforehand is unverified regardless of what passes after.

---

## 10. What this plan will not claim

- Completing it does not make the codebase correct. It closes defects found in regions examined, for classes hunted.
- Generated directories are never audited.
- `[UNK]` findings, expected to be concentrated in O1, are unresolved, not clean.
- Frontend runtime behavior under real browsers beyond Chromium is unexamined.
- The 9 open escalations from `docs/plans/backend-defect-remediation.md` are **not** in this plan's scope. They are separate, already-documented work.

**Expected honest outcome:** a partial hunt with an explicit coverage statement, as V7 intends. The backend hunt spent 78 candidates to find 37 confirmed defects and clear 33; a similar ratio here would be a good result, and a lower one would still be informative about where this codebase's risk actually sits.
