# Pre-Existing Issues — Remediation Plan

**Date:** 2026-08-16
**Status:** Draft for review
**Branch target:** `fix/pre-existing-debt`
**Scope:** issues found incidentally while implementing [`agent-native-reasoner-v2.md`](agent-native-reasoner-v2.md). None were caused by that work; none block it.

---

## 0. Verified findings

Each item was read out of the tree on 2026-08-16. Two findings I reported verbally were **wrong on inspection** and are recorded here as non-issues so nobody re-opens them.

| # | Issue | Severity | Evidence |
| --- | --- | --- | --- |
| 3 | Two `check_rate_limit` implementations with different bucketing, both live — authenticated callers bucketed by IP on five routes, by account on the rest | **Medium — live bug** | `api/auth_deps.py:92`, `api/dependencies.py:342` |
| 1 | `domain.preset_core` imports `core.ports.model_registry_port`, breaking the layers contract | Low — already CI-gated | `.importlinter:12-25`, `src/reasoner/domain/preset_core.py:307` |
| 2 | `CLAUDE.md` claims "Known violations: none currently open" — false while #1 stands | Low | `CLAUDE.md` §1 |
| 4 | `test_saas_auth_integration.py::test_run_pipeline_with_auth_token` fails without Postgres | Low | `tests/test_saas_auth_integration.py:110` |
| 5 | Stale worktree `.claude/worktrees/elated-shamir-cc7852/` holding a full `src/reasoner` copy | Low | `Glob **/core/settings.py` |

Numbering follows my original report; the table is ordered by what actually matters. Only #3 is wrong in running code — the rest are config, docs, test hygiene, and housekeeping.

### Corrected non-findings

- **`test_cross_process_cancel_via_redis` is not a defect.** It is already marked `@pytest.mark.integration` with a comment explaining precisely why (`tests/test_saas_run_state.py:127-132`). It failed for me only because I invoked it by explicit path, which bypasses the `-m "not slow and not integration"` filter CI uses. Working as designed — no action.
- **Neither `check_rate_limit` is dead code.** I initially said `auth_deps.py`'s "looks unused". It is used by `routes/uploads.py`, `routes/keys.py`, `routes/credits.py`, `routes/account_keys.py`, `routes/images.py`. The `dependencies.py` one is used by `routes/feedback.py`, `routes/errors.py`, `routes/agent.py`, `routes/context.py`, and `/api/run`. The real issue is divergence, not deadness — see #3.

---

## 1. Principles

1. **Smallest correct change.** This is debt cleanup, not a refactor. Nothing here should touch behaviour a user can observe, except #3 where changing behaviour *is* the fix.
2. **Match existing precedent over inventing patterns.** `.importlinter` already carries commented `ignore_imports` entries for two sibling `domain.preset_core -> core.*` edges (`:91-93`); #1's resolution should look like those or deliberately reject that approach with a reason.
3. **Fix or document — never silently tolerate.** An `ignore_imports` line with a comment is a decision. An undocumented violation is rot.
4. **Sequence by risk.** #2 and #5 are trivial and independent. #1 is a judgement call. #3 touches request admission on every route and goes last, alone.

---

## 2. Issue #1 — `domain → core` layer violation

### What is actually happening

`PipelinePreset.__post_init__` calls `_derived_env_vars()`, which reaches through `ModelRegistryPort` to ask the registry which env var each routed model needs. The method's own docstring shows the author already thought about layering:

> *Goes through ModelRegistryPort rather than importing infrastructure.llm.registry: domain must not depend on infrastructure.*

So this is not carelessness — it is a deliberate choice that avoided the *worse* violation (`domain → infrastructure`) and landed on a lesser one (`domain → core`) that the contract still forbids. The feature it enables is real: without it `required_env_vars` was always empty and `check_keys()`/`missing_keys()` were silently no-ops for every preset.

### Three options

| Option | Change | Verdict |
| --- | --- | --- |
| **A. Add `ignore_imports` entry** | One line in `.importlinter`, with a comment | Cheapest; matches the file's own precedent at `:91-93`. But it grows the exception list, and exceptions are how a layered contract dies by a thousand cuts. |
| **B. Invert with a setter** | Domain exposes `set_env_var_resolver(fn)`; a composition root injects a callable. Domain imports nothing. | Architecturally clean, mirrors `core/search.py`'s `set_build_provider()` precedent. Costs a new injection point in three composition roots (`api/__init__.py`, `main.py`, `headless.py`). |
| **C. Move derivation out of domain** | `PipelinePreset` stops deriving; `PresetService` (application layer) computes `required_env_vars` and sets them | Removes the import entirely and puts registry-aware logic in the layer that already talks to the registry. Changes when derivation happens — construction-time becomes service-time. |

### The deciding fact: `PRESETS` is built at module import

`src/reasoner/presets.py:25` runs `PRESETS = {p.id: p for p in _all_presets}` at **import time**, so every `PipelinePreset.__post_init__` — and therefore every `_derived_env_vars()` call — fires the moment `reasoner.presets` is first imported. That is long before any composition root calls an injector.

This settles the choice:

- **Option B is not viable as stated.** A `set_env_var_resolver()` hook would be `None` at the only moment it is consulted, so `_derived_env_vars()` returns `[]` for every preset and `check_keys()` silently reverts to the no-op the feature was written to fix. B trades a visible contract violation for an invisible dead feature — strictly worse.
- The same timing already explains the existing `try/except RuntimeError: return []` in the current code: on CLI and test paths the registry port genuinely is not injected yet, and the author accepted degraded preflight there. B would make that the case *everywhere*, not just those paths.

B could be rescued by making preset construction lazy (build `PRESETS` on first access rather than at import), but that is a substantially larger change to a module with 40 lines of someone else's uncommitted work in it — out of proportion to the problem being solved.

### Recommendation: **A** — documented `ignore_imports` entry

`.importlinter` already carries exactly this pattern for two sibling edges, with a section comment (`:91-93`):

```
    # ── domain → core (TYPE_CHECKING + preset/model constants) ──
    reasoner.domain.preset_core -> reasoner.core.constants_models
    reasoner.domain.preset_core -> reasoner.core.protocol
```

Add a third under its own comment naming *why* this one exists and what would retire it:

```
    # domain → core: preset key-preflight derivation. PRESETS is built at
    # module import (presets.py:25), so DI cannot reach it — a resolver hook
    # would always be unset at call time. Retire this by making preset
    # construction lazy, then injecting.
    reasoner.domain.preset_core -> reasoner.core.ports.model_registry_port
```

This is a real exception with a stated retirement path, not a silenced warning.

**Do not take C** without separate discussion: moving derivation to service-time means a `PipelinePreset` constructed directly (CLI, tests, `presets.py` module import) no longer self-describes its key requirements, which is a behaviour change disguised as a refactor.

### The exception-count ratchet

`pr-architecture.yml:33-45` counts `->` lines in `.importlinter` and fails above `MAX=65`, with an instruction to ratchet *down*, never up without a tracking issue. **Check the current count before adding a line** — if it is already at 65, adding one fails CI, and the correct move is to retire an obsolete exception in the same PR rather than raising the cap.

### Files touched (option A)

| File | Change |
| --- | --- |
| `.importlinter` | One `ignore_imports` line + comment |
| `CLAUDE.md` | §1 names the accepted exception (see #2) |

### Verification

- `lint-imports` reports **Contracts: 1 kept, 0 broken**.
- Exception count stays ≤ 65 (`grep -c '\->' .importlinter`).
- `python scripts/check_no_registry_bypass.py` still exits 0 — unaffected, it only forbids direct `infrastructure.llm.registry` imports.
- Worth adding regardless of option: a test pinning that `required_env_vars` is populated when the registry port *is* injected. The docstring promises this; nothing currently checks it.

**Risk:** low. One config line and a doc sentence, no code path changes.

---

## 3. Issue #2 — stale architecture claim in `CLAUDE.md`

`CLAUDE.md` §1 states: *"Known violations (last verified 2026-08): none currently open."*

Untrue while #1 stands. Worse than a missing note, because it tells the next reader (human or agent) not to bother checking.

**Fix:** one sentence, in the same PR that resolves #1, naming the accepted exception and its retirement path.

### CI already enforces this — and that reframes the whole finding

`pr-architecture.yml` runs `lint-imports --no-cache` on every PR to `main` (`:24`), with `import-linter==2.12` / `grimp==3.14` pinned deliberately, plus the AST bypass guard and the exception-count ratchet. So the contract is enforced.

Which means **this violation would have been caught the moment the in-progress `preset_core.py` work was opened as a PR.** It is not undetected rot — it is uncommitted work that has not reached its gate yet. That lowers the urgency of #1 considerably and changes who should fix it: whoever owns that uncommitted change, as part of landing it, not a separate cleanup PR racing them to the same file.

The genuinely useful contribution here is therefore the *analysis* — that DI cannot solve it because `PRESETS` builds at import time, and that option A with a retirement note is the honest resolution. Hand that to whoever owns the change rather than editing `preset_core.py` underneath them.

---

## 4. Issue #3 — duplicated `check_rate_limit`

### The divergence

| | `api/auth_deps.py:92` | `api/dependencies.py:342` |
| --- | --- | --- |
| Bucket key | IP + User-Agent hash, always | `user:{id}` when authenticated, else IP + UA hash |
| Limiter call | `is_allowed(client_id)` | `is_allowed_for_user(client_id, tier=...)` when authed |
| On limiter error | 503 (infrastructure failure) | Fail closed → 429 |
| Used by | uploads, keys, credits, account_keys, images | feedback, errors, agent, context, `/api/run` |

Two routes can therefore be rate-limited under *different identities* for the same caller: an authenticated user hitting `/api/run` is bucketed per-account, but hitting `/api/upload` is bucketed per-IP. Two users behind one NAT share the upload budget; one user across two IPs gets double.

### Why this matters beyond tidiness

It is a quota-fairness bug and a mild abuse vector: the IP-keyed path is the weaker guarantee, and it guards uploads and key-validation — exactly the endpoints where per-account attribution matters most.

### Recommendation

Converge on the `dependencies.py` implementation (user-aware, fail-closed) and make `auth_deps.check_rate_limit` a thin re-export, then migrate call sites in a second pass.

**Pattern: Strangler.** Do not edit five route files and delete a function in one commit.

1. **Commit 1** — `auth_deps.check_rate_limit` delegates to `dependencies.check_rate_limit`. Behaviour of the five routes changes to user-aware bucketing; nothing else moves. One revert undoes it.
2. **Commit 2** — update the five route modules to import from `dependencies` directly.
3. **Commit 3** — delete the delegating shim.

Splitting this way means the behaviour change and the mechanical import churn are reviewable independently, and a regression in step 1 is not tangled up with 20 import edits.

### Watch for

- **Circular import.** `auth_deps` and `dependencies` both sit in `api/`; confirm `dependencies` does not import `auth_deps` before adding the delegation. If it does, invert the direction (make `dependencies` the shim) rather than adding a lazy import to paper over a cycle.
- **The 503-vs-429 difference is real.** `auth_deps` returns 503 when the limiter itself errors; `dependencies` fails closed to 429. Converging means uploads start returning 429 where they returned 503. Deliberate and defensible — a caller cannot distinguish "limiter is down" from "you are limited", and fail-closed is the safer default — but it is an observable API change and belongs in the PR description, not discovered by a client.

### Verification

- Existing rate-limiter tests pass unchanged (`tests/test_saas_rate_limit_user.py`).
- New test: an authenticated caller hitting an `auth_deps`-guarded route is bucketed by user id, not IP.
- Manual: two requests from different IPs with the same key share one budget.

**Risk:** medium. This is request admission on every route. Ship it alone, not bundled.

---

## 5. Issue #4 — Postgres-dependent test in the default lane

`test_run_pipeline_with_auth_token` asserts 200 but gets 402: no local Postgres → subscription lookup fails → tier defaults to FREE → credit gate rejects.

Note the failure is *two* fallbacks deep — the test does not fail because Postgres is missing, it fails because a chain of graceful degradations lands on "no credits". That is worth knowing: the same chain runs in production if the subscription DB blips.

**Options:**
- **A.** Mark `@pytest.mark.integration`, matching how `test_saas_run_state.py:130` handled the identical situation. Consistent with existing precedent, one line.
- **B.** Stub the credit gate in the test so it exercises auth (its actual subject) without needing a ledger.

**Recommendation: B, falling back to A.** The test's name and position say it is about *auth*, not billing. A credit gate failing it is incidental coupling. If stubbing proves fiddly, A is fine and consistent.

Either way, add a one-line comment naming the dependency — the next person to hit a bare 402 should not have to trace two fallbacks to understand why.

**Risk:** none. Test-only.

---

## 6. Issue #5 — stale worktree

`.claude/worktrees/elated-shamir-cc7852/` holds a frozen copy of `src/reasoner`, including its own `core/settings.py`.

It caused no actual harm — it does not shadow imports (`sys.path` and `.pth` files were checked; it appears on neither) — but it cost real time during a `Glob` sweep, surfacing as a plausible-looking second `settings.py` while I was chasing an unrelated phantom bug.

**Before deleting:** run `git worktree list`. If git still tracks it, `git worktree remove` is the correct removal; a bare `rm -rf` leaves a dangling administrative entry in `.git/worktrees`. If git does not know about it, it is orphaned and safe to remove directly.

**Do not delete without checking for uncommitted work inside it.** A worktree is where someone parks work in progress. `git -C .claude/worktrees/elated-shamir-cc7852 status` first.

**Risk:** low, conditional on the check above. **This one needs an explicit go-ahead** — deleting someone's parked work to tidy a directory listing is not a trade worth making silently.

---

## 7. Sequencing

All four remaining items are independent. Nothing blocks anything.

```
#1 + #2  ← hand to the owner of the uncommitted preset_core.py work; not a separate PR
#4       ← independent, trivial, test-only
#5       ← independent, needs an explicit go-ahead
#3       ← last, alone, three commits — the only one with real blast radius
```

| Item | PRs | Risk | Gate |
| --- | --- | --- | --- |
| #1 layer violation + #2 doc | 1 (folded into the owner's in-flight work) | Low | `lint-imports` 1 kept / 0 broken; exception count ≤ 65 |
| #4 test dependency | 1 | None | Default lane green without Postgres |
| #5 worktree | 1 | Low | `git worktree list` clean |
| #3 rate limiter | 3 commits, 1 PR | Med | Rate-limit tests pass; user-bucketing test added |

**If only one of these gets done, make it #3.** It is the only item that is currently wrong in production rather than wrong in a config file or a doc: authenticated callers are bucketed by IP on five routes and by account on the rest, which is a live quota-fairness bug. #1 is already gated by CI, #2 is a stale sentence, #4 is test hygiene, #5 is housekeeping.

---

## 8. Explicitly out of scope

- **The rest of the uncommitted work on this branch.** `git diff HEAD` shows substantial in-progress changes to `preset_core.py`, `Composer.tsx`, encryption, and more, by someone else. #1 touches `preset_core.py` and will need coordinating with whoever owns that work — **check before starting**, since a conflicting edit to a file with 40 uncommitted lines is a merge headache for both parties.
- **`ui-next/src/components/layout/Composer.tsx`** — carries pre-existing TypeScript errors (`Expected 2 arguments, but got 1`, lines 426 and 451), confirmed via `git stash` to predate this session. Not touched, not fixed; belongs to the in-progress work above.
- **`ruff` debt in `api/__init__.py`** — 115 findings (46 `E402`, 28 `F401`, 28 `I001`). Almost entirely import-ordering artifacts of a 1000-line module that does sequenced startup wiring, where import order is load-bearing. Auto-fixing would be a large, risky diff for zero behaviour gain. Leave it, or address it as part of a deliberate decomposition of that module — not as drive-by cleanup.
