# Safe Integration Plan — Working-Tree Drift + 2 Leftover Branches

**Status:** Draft · **Date:** 2026-06-26 · **Branch base:** `main` @ merged PR #5
**Goal:** Land all genuinely-valuable uncommitted code and leftover-branch work into `main` **without breaking the green build**, by untangling it into coherent, individually-tested units.

---

## 0. Core Problem & Guiding Principles

The working tree is **not one feature** — it is several **half-committed features tangled together** (27 modified + 3 untracked `src` files). We already hit the failure mode this causes twice: commit `2988f9d` landed `pipeline.py`'s *use* of `PHASE_REASONING_EFFORT` but left the *definition* uncommitted → green-locally / red-on-CI. The `ports/__init__.py` TranslationPort export is the same trap, still latent.

**Principles (non-negotiable):**

1. **Atomic feature commits.** Every commit must contain *all* files a feature needs to import and run. Never split a definition from its consumer. (This is the root-cause lesson of `2988f9d`.)
2. **One feature → one branch → one PR.** Never bundle unrelated clusters. Small reviewable units, each independently revertible.
3. **Green gate per unit.** After staging a cluster, run the full verification gate (below) *before* committing. Merge only on green CI.
4. **Prefer `main` as truth.** Where a leftover branch conflicts with main, main wins unless the branch demonstrably fixes a still-present bug.
5. **No bulk `git merge` of stale branches.** Salvage by cherry-pick / manual port, never wholesale.
6. **Backup before mutating.** Tag/stash before each destructive step; everything reversible.

**Verification gate (run for every unit):**
```bash
# from repo root, env as CI uses
PYTHONPATH=src CSRF_ENFORCE_BACKEND=false python -m pytest tests/unit/ -q          # fast inner loop
PYTHONPATH=src lint-imports --no-cache                                              # layering gate
PYTHONPATH=src python -c "import reasoner.application.pipeline; import reasoner.api"  # import smoke
# full gate before PR merge:
PYTHONPATH=src CSRF_ENFORCE_BACKEND=false python -m pytest tests/ -m "not slow and not integration and not searxng" -q
```
**Windows note:** run `lint-imports` via PowerShell, never the rtk-proxied Bash (it 0-byte-captures stdout). Pin stays `import-linter==2.12 grimp==3.14`.

---

## 1. Inventory (what we are integrating)

### 1A. Working-tree clusters (untracked + modified `src`)

| # | Cluster | Files | Completeness signal | Risk |
|---|---------|-------|--------------------|------|
| C1 | **Execution refactor** — split streaming monolith | `api/execution/pipeline.py` (±1003), **new** `api/execution/{cancel,direct,web_search}.py` | `pipeline.py` imports `.direct`/`.web_search`; deps (`sse_utils._broadcast_ws/_event`, `SearchService.stream_web_search_results`) exist on main. `cancel.py` (`StreamingConnectionContext`) **import site unconfirmed**. Public `PipelineExecutionService` consumed by `api/streaming.py` — **interface must be preserved**. | High (large, public interface, partial-commit trap if 3 new files not committed with pipeline.py) |
| C2 | **Reasoning-effort completion (port side)** | `core/ports/llm_port.py` (+`call_with_tools`), `core/ports/__init__.py` (TranslationPort export), `infrastructure/llm/{router,openai_compat,base}.py`, `core/constants_models.py` | Pairs with already-merged `temperatures.py`/`protocol.py`/`executor.py`. `executor.py` reads effort defensively; this cluster is the deeper provider wiring. | Med (touches hot LLM path) |
| C3 | **Telemetry / persistence** | `healing/telemetry_exporter.py`, `infrastructure/persistence/{event_store,error_store,feedback_store,telemetry_store}.py`, `application/services/scorecard_service.py` | Likely harness-telemetry follow-ups. | Med (DB writes) |
| C4 | **Misc small** | `api/routes/gdpr.py`, `application/flows/{brainstorming_phases,dialectical_phases}.py`, `application/services/{data_eraser,serializers}.py`, `core/rerank.py`, `documents/vector_store.py`, `infrastructure/redis/run_state.py`, `infrastructure/server_check.py`, `main.py`, `phases/brainstorming.py`, `presets.py` | Assorted small edits; must be sub-grouped by real intent during Phase 2. | Low–Med |
| C0 | **Junk (never commit)** | `*.db`, `*.db-shm`, `*.db-wal`, `cache/**`, `graphify-out/**`, `src/reasoner/cache/**`, `src/reasoner/history/**` | Runtime artifacts. | n/a (gitignore) |

> Cluster boundaries above are a **hypothesis from import-graph + diff-size**. Phase 2 Step A re-derives them from actual diff content before any commit.

### 1B. Leftover branches

| Branch | vs current main | Verdict | Rationale |
|--------|-----------------|---------|-----------|
| `fix/import-linter-toolchain` | +1 / −1; touches `.importlinter`, `pr-architecture.yml`, `hyper_agent.py` | **DISCARD** | A *competing* import-linter fix. Main already has a working, CI-green gate (from PR #5). Its `hyper_agent.py` differs from main's working version → merging would revert/conflict the live gate for zero gain. Document + delete. |
| `fix/autonomous-bug-fixes-session` | +2 / −2; 11 code files incl. `csrf.py` (+29), `rate_limiter.py` (+58), `postgres_store.py` (+61), `event_store.py`, `streaming.py`, `auth_deps.py`, `token_cache.py`, `uploader.py` | **SALVAGE SELECTIVELY** | 2-month-old (Apr 25), diverged. Some changes may already be in main or be superseded. Real bug-fix candidates (rate limiter, postgres, csrf) worth porting *if still applicable*. Per-file triage, cherry-pick the live ones only. |

---

## 2. Phased Execution

### Phase 0 — Prep & make the tree legible (no code changes)

0.1 **Safety tag** of current state:
```bash
git tag pre-integration-backup
git stash list   # note existing stash@{0} "goal-hook" — drop later if redundant
```
0.2 **Quarantine the junk so `git status` is readable** (its own tiny PR, merge first):
- Add to `.gitignore`: `cache/`, `graphify-out/`, `*.db`, `*.db-shm`, `*.db-wal`, `src/reasoner/cache/`, `src/reasoner/history/`.
- `git rm -r --cached` the already-tracked junk (`cache/`, `graphify-out/`, `feedback.db`, …) — removes from tracking, keeps on disk.
- Verify `git status` now shows **only** real source drift. Commit on `chore/gitignore-generated-artifacts` → PR → merge.
0.3 **Baseline**: capture current green gate output (`pytest tests/unit/` = 232 passed) as the regression reference.

### Phase 1 — Re-derive true clusters (analysis, no commits)

For each modified file, read the actual diff and tag it to a feature (C1–C4) — correct the hypothesis in §1A. Produce a definitive file→cluster map. Specifically resolve:
- Whether `cancel.py`'s `StreamingConnectionContext` is imported by the refactored `pipeline.py` (if not, the refactor is incomplete → must wire or drop it).
- Whether C2's `router/openai_compat/base` edits are *only* reasoning-effort or also carry unrelated changes (split if mixed).
- Sub-group C4 by intent (don't commit 11 unrelated one-liners as one blob).

### Phase 2 — Integrate working-tree clusters, one at a time

Order: **least-coupled → most-coupled** to surface breakage early on small units.
Suggested order: **C4 sub-groups → C3 → C2 → C1** (C1 last: largest, public interface).

Per cluster, the **loop**:
```
a. Branch:        git switch -c feat/<cluster> main
b. Stage ONLY that cluster's files (atomic — definition + consumers together):
                  git add <exact files>
c. Gate:          run the §0 verification gate
d. If red:        diagnose; the cluster is incomplete → find the missing file(s)
                  still in the working tree and add them (this is the 2988f9d lesson).
e. Tests:         add/adjust unit tests for new behavior (esp. C1 streaming paths,
                  C2 effort injection). Coverage must not drop below the 30% floor.
f. Commit + push + open PR; merge on green CI.
g. Return to `main`, pull, repeat for next cluster.
```
**C1-specific guardrails:**
- Commit `pipeline.py` + `cancel.py` + `direct.py` + `web_search.py` **in the same commit** (atomic; pipeline.py imports the new modules).
- Assert `PipelineExecutionService` public signature unchanged (grep consumers in `api/streaming.py`); add a smoke test that imports it and that `streaming.run_stream` still wires.
- Manually exercise: direct-answer path, web-search path, cancel path (the three extracted concerns).

**C2-specific guardrails:**
- Confirm `llm_port.call_with_tools` additions are matched by an implementation in `router`/providers (protocol vs impl parity), else import-time `TypeError`/abstract errors.
- Commit `ports/__init__.py` TranslationPort export here (closes the latent partial-commit) — verify `from reasoner.core.ports import TranslationPort` works.

### Phase 3 — Salvage `fix/autonomous-bug-fixes-session`

3.1 **Per-file triage** (branch is stale; main has moved):
```bash
for f in csrf.py rate_limiter.py postgres_store.py event_store.py streaming.py \
         auth_deps.py token_cache.py uploader.py cached_quota_repo.py hyperagent.py; do
  git diff main fix/autonomous-bug-fixes-session -- <path>/$f
done
```
For each file decide: **(a) already in main** (skip), **(b) live bug fix not in main** (port), **(c) superseded/obsolete** (drop). Record the verdict per file.
3.2 **Port the keepers** onto a fresh `fix/salvaged-bugfixes` branch off main via **manual edit or `git cherry-pick -n` then prune** — never merge the whole branch (drags Apr-era `cache/`/`history/` junk + stale siblings).
3.3 Prioritize security-relevant keepers (`csrf.py`, `rate_limiter.py`, `auth_deps.py`): these get a **security re-review** and explicit tests before commit.
3.4 Gate → PR → merge. Then delete the stale branch (local + origin).

### Phase 4 — Retire `fix/import-linter-toolchain`

4.1 Confirm main's gate is green and equal-or-better (it is: PR #5 made it KEPT/0-broken).
4.2 Document the decision (one line in this file's changelog + PR description if a branch-cleanup PR is used).
4.3 Delete branch local + origin:
```bash
git branch -D fix/import-linter-toolchain
git push origin --delete fix/import-linter-toolchain
```

### Phase 5 — Final cleanup & verification

5.1 Drop redundant `stash@{0}` (goal-hook backup) once all clusters are committed.
5.2 Delete stale scratch branches/worktrees: `worktree-agent-*` (6), `claude/gallant-darwin-*`, and any local-only fully-merged branches.
5.3 **Full-suite verification on main**:
```bash
PYTHONPATH=src CSRF_ENFORCE_BACKEND=false python -m pytest tests/ -m "not slow and not integration and not searxng" -q
PYTHONPATH=src lint-imports --no-cache         # KEPT, 0 broken
```
5.4 Confirm all CI checks green on main. Remove `pre-integration-backup` tag once satisfied.
5.5 Update `docs/CODEBASE_MINDMAP.md` / `AGENTS.md` for any new public surface (execution modules, effort knob).

---

## 3. Risk Register & Rollback

| Risk | Likelihood | Mitigation | Rollback |
|------|-----------|------------|----------|
| Partial-commit (definition without consumer) → green-local/red-CI | High (already happened ×2) | Atomic cluster commits; import-smoke in gate; CI before merge | `git revert <commit>`; cluster is isolated |
| C1 breaks `PipelineExecutionService` public contract → streaming 500s | Med | Interface-preservation assertion + streaming smoke test | revert C1 PR; main unaffected |
| C2 protocol/impl mismatch (`call_with_tools`) | Med | Parity check protocol↔provider before commit | revert C2 PR |
| Stale branch reintroduces old bug / conflicts with main evolution | Med | Per-file triage, never bulk-merge; security re-review | drop the keeper; no branch merge to undo |
| Lost work if a cluster is mis-scoped | Low | `pre-integration-backup` tag holds the full pre-state | `git checkout pre-integration-backup -- <file>` |
| Gitignore `rm --cached` removes a file that *should* be tracked | Low | Review the `rm --cached` list before commit | restore from tag |

**Global rollback:** every step is its own PR/commit; `git revert` any single unit. `pre-integration-backup` tag preserves the exact pre-integration working tree + index.

---

## 4. Definition of Done

- [ ] Junk gitignored; `git status` shows only intentional changes.
- [ ] C1–C4 each merged via own green PR; working tree has **no uncommitted `src` code** (only regenerable artifacts).
- [ ] Valuable `autonomous-bug-fixes` changes ported + tested; branch deleted.
- [ ] `import-linter-toolchain` deleted with documented rationale.
- [ ] Stale worktree/scratch branches removed; `stash@{0}` dropped.
- [ ] Full non-integration suite green on `main`; `lint-imports` KEPT/0-broken; CI green.
- [ ] Docs updated for new public surface.

---

## 5. Open Questions (resolve in Phase 1)

1. Is `cancel.py`/`StreamingConnectionContext` actually wired into the refactored `pipeline.py`, or dead? (Determines whether C1 ships it or drops it.)
2. Do `router/openai_compat/base` edits carry non-effort changes that belong to C3 or a 5th cluster?
3. Which `autonomous-bug-fixes` files are already represented in main by an equivalent fix? (Triage table output.)
4. Does `llm_port.call_with_tools` have a live implementer, or is it a forward-declared protocol method with no consumer yet? (Ship vs hold.)
