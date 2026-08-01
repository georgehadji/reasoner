# Reasoner — Production Readiness Implementation Plan

**Status:** Draft for review
**Created:** 2026-07-29
**Baseline commit:** `7e9f261` (`main`)
**Scope:** Every fix, addition and enhancement identified in the 2026-07-29 production-readiness audit, plus the xAI search integration.

---

## 0. How to read this document

Every work item below carries:

| Field | Meaning |
|---|---|
| **Problem** | What is actually wrong |
| **Evidence** | How it was verified, and with what command — so you can reproduce it |
| **Approach** | What to build |
| **Paradigm / Pattern** | The design choice *and why that one*, not a default |
| **Touches** | Files and modules |
| **Verify** | The check that proves it works |
| **Rollback** | How to undo it |
| **Size** | S ≈ ½–1 day · M ≈ 2–4 days · L ≈ 1–2 weeks (one engineer) |

**Confidence labels** follow the project's own epistemic convention:

- `VERIFIED` — reproduced in this session against `main` with a named command.
- `HYPOTHESIS` — strongly indicated but not executed end-to-end.
- `UNKNOWN` — needs investigation before the item can be scoped.

Do not treat `HYPOTHESIS` items as ready to implement. Scope them first.

---

## 1. Verified current state

All measured on `main` @ `7e9f261` unless noted.

| Metric | Value | Confidence |
|---|---|---|
| Python source | 62,898 LOC across 467 files | `VERIFIED` |
| Files over 800 lines | 6 | `VERIFIED` |
| Tests collected | 3,301 | `VERIFIED` |
| Tests failing (serial, CI env, `not slow and not integration`) | 125 | `VERIFIED` |
| `ruff F821` (undefined names) | 37 — **all** deferred annotations, zero runtime | `VERIFIED` |
| `ruff` total lint findings | 1552 `W293`, 1419 `E501`, 737 `F401`, 411 `I001` | `VERIFIED` |
| `import-linter` layering exceptions | 59 | `VERIFIED` (config read) |
| Presets failing project's own validator | 4 of 50 | `VERIFIED` |
| npm vulnerabilities | 9 high, 6 moderate, 1 low | `VERIFIED` |
| Secrets scan | clean | `VERIFIED` |
| `docker build` | succeeds, exit 0 | `VERIFIED` |
| `docker compose up` | **cannot boot** — see F-01 | `VERIFIED` |
| CI | every job fails in 2–3s with zero steps executed | `VERIFIED` |

### Already completed this session

SearXNG fully removed on branch `chore/remove-searxng` (46 files, +406/−1523): image and video widgets ported to the Brave Search API with new `search_images()` / `search_videos()` adapter methods, `DiscoveryClient`/`SearXNGAdapter` deleted, CLI and headless `web_search` routes repointed to `get_search_client()`, CI job and pytest marker removed, docs updated, 14 new tests added. Net failure delta vs `main`: −3 (one introduced regression found by set-diffing failure names, fixed). **Not yet merged.**

This plan assumes that branch lands first. Several items below depend on it.

---

## 2. Architectural ground rules

These are constraints on *how* the work below is implemented. They are not negotiable per-item.

### 2.1 Dependency rule (existing, enforced by `import-linter`)

```
api → application → infrastructure → core → domain
```

Domain depends on nothing. Core defines ports. Infrastructure implements ports. Nothing inner imports outward. Every new module below states which layer it lands in.

### 2.2 Composition root

New rule introduced by this plan. **Configuration is resolved once, at process start, and injected downward.** No module reads `os.environ` at import time. No module derives a filesystem path from `__file__`. The composition root is `asgi.py` for the server and `main.py` for the CLI.

This is the single change that unlocks F-02, F-05, F-09 and most of the test-suite triage — module-level environment reads are why tests need `JWT_SECRET_KEY` set merely to *collect*.

### 2.3 Fail loud at boundaries, degrade gracefully inside

- **Boundary** (config load, provider capability check, migration state): raise. A misconfigured production process must not start.
- **Inside** (a search backend times out, one perspective model fails): degrade and record. The pipeline is explicitly designed to survive partial failure.

The current codebase inverts this in places — F-05 (no config validation) and E-03 (silent capability loss) are both boundary failures being handled as if they were internal ones.

### 2.4 Every phase is independently revertible

One PR per work item, or per tightly-coupled group. No PR merges unless:

1. Test failures ≤ baseline (compare **failure name sets**, not counts — counts hide a swap)
2. `import-linter` exceptions ≤ baseline
3. Lint ratchet not increased (§8.2)
4. `docker compose config` still resolves

---

## 3. Phase 0 — Unblock (nothing else matters first)

### F-00 · Restore CI execution

**Problem.** Every GitHub Actions job fails 2–3 seconds after queueing.
**Evidence.** `VERIFIED` — `gh api repos/<owner>/<repo>/actions/jobs/88600299321` returns `"conclusion": "failure"` with `"steps": []`. Jobs never start. Consistent with an account-level billing or quota block, though the specific cause was not confirmed from the API.
**Approach.** Resolve the account billing state. Confirm by re-running one workflow and observing non-empty `steps`.
**Verify.** `gh run list --limit 1` shows a run with executed steps.
**Size.** S (administrative)
**Blocks.** Everything in §4 onward. There is no point hardening gates that cannot execute.

---

## 4. Phase 1 — Deployment correctness (P0)

These three items are why the product cannot be deployed today.

### F-01 · `docker compose up` never boots

**Problem.** The cert-generator service uses `$service` (single `$`) inside a YAML block scalar. Docker Compose interpolates `$service` at **parse** time as a Compose variable, not at runtime as a shell variable. It resolves to empty.

**Evidence.** `VERIFIED` — `docker compose config` resolves the command to:

```sh
for service in backend frontend postgres redis; do
  openssl genrsa -out /certs/.key 2048 &&
  openssl req -new -key /certs/.key -out /certs/.csr -subj "/CN=" &&
  ...
  (echo "subjectAltName = DNS:, DNS:localhost" > /certs/extfile.cnf && ...)
done
```

All four iterations write the same nameless `/certs/.key` and `/certs/.crt`, with an empty CN and empty SAN. Compose also emits `warning: The "service" variable is not set` ten times per invocation.

**Consequence chain.** `/certs/postgres.crt` and `/certs/redis.crt` are never created → Postgres (`-c ssl_cert_file=/certs/postgres.crt`) and Valkey (`--tls-cert-file /certs/redis.crt`) fail to start → both are `condition: service_healthy` dependencies of `backend` → the backend never starts. The stack does not come up at all.

**Approach.** Escape as `$$service` so Compose passes a literal `$service` to the shell. Then reconsider the whole approach: generating a CA and four leaf certs inside an `alpine` container with an inline 18-line shell one-liner is fragile by construction.

**Paradigm / Pattern.** Replace the inline scalar with a checked-in `scripts/gen-internal-certs.sh` mounted into the container. Rationale: **executable specification** over embedded string. A shell script is lintable (`shellcheck`), testable in isolation, and diffable; an escaped YAML block scalar is none of those and this bug is the direct cost of that. Keep the container ephemeral and idempotent (`if [ ! -f ca.key ]`) — that part of the current design is correct.

**Touches.** `docker-compose.yml`, new `scripts/gen-internal-certs.sh`.

**Verify.**
```bash
docker compose config | grep -c 'certs/backend.key'   # must be ≥ 1, currently 0
docker compose up -d && docker compose ps             # all services healthy
docker compose exec backend openssl x509 -in /certs/backend.crt -noout -subject -ext subjectAltName
```
Add a CI job asserting `docker compose config` contains no `/certs/.key` and emits no `variable is not set` warnings. This bug class is invisible to YAML linting and must be caught by resolution.

**Rollback.** Revert the compose file; the stack is already broken, so there is no working state to lose.
**Size.** S

---

### F-02 · All persistent state is written inside the package; volume mounts are dead

**Problem.** Six stores anchor their paths to `Path(__file__)`, i.e. inside the installed package, while `docker-compose.yml` mounts volumes at `/app/cache`, `/app/history`, `/app/uploads`. Nothing writes to those paths. Every rebuild destroys all state.

**Evidence.** `VERIFIED` — present on `main`:

| Path written | Source |
|---|---|
| `src/reasoner/cache/` | `api/cache.py:17` |
| `src/reasoner/infrastructure/uploads/` | `infrastructure/uploader.py:56` |
| `src/errors.db` | `infrastructure/persistence/error_store.py:74` |
| `src/feedback.db` | `infrastructure/persistence/feedback_store.py:64` |
| `src/reasoner/events.db` | `infrastructure/persistence/event_store.py:38` |
| `src/reasoner/auth_keys.db` | `core/settings.py:118` (`AUTH_DB_PATH` default) |

Container `WORKDIR` is `/app` with code at `/app/src/reasoner`, so `Path(__file__).parent.parent / "cache"` resolves to `/app/src/reasoner/cache` — not the mounted `/app/cache`. Corroborating symptom: untracked `src/reasoner/uploads/` and `src/reasoner/.upload_hash_index.json` appear in `git status` on a working checkout — runtime state leaking into the source tree.

**Approach.** Introduce a single resolved path object; inject it.

```python
# core/paths.py  — Core layer, no outer dependencies
@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path
    cache: Path
    uploads: Path
    history: Path
    events_db: Path
    errors_db: Path
    feedback_db: Path
    auth_db: Path

    @classmethod
    def from_root(cls, root: Path) -> DataPaths: ...
    def ensure(self) -> None:
        """Create every directory. Called once, at the composition root."""
```

`DATA_DIR` env var, default `./data` in development and `/app/data` in the container. Every store already accepts `db_path: str | Path | None = None` in its constructor (confirmed at `error_store.py:68-74`) — so this is a **constructor-injection change at the call sites**, not a rewrite of the stores. Delete the `Path(__file__)` fallbacks so the ambient default cannot silently return.

**Paradigm / Pattern.** **Value Object** (frozen dataclass, no behaviour beyond derivation) + **Dependency Injection** from the composition root. Explicitly *not* a singleton or a module-level global: ambient global path state is the current bug, and a singleton would preserve it under a nicer name. Frozen because a path set that mutates mid-process is never correct and makes test isolation impossible.

**Touches.** New `core/paths.py`; `api/cache.py`, `infrastructure/uploader.py`, `infrastructure/persistence/{error_store,feedback_store,event_store}.py`, `core/settings.py`, `asgi.py`, `main.py`, `docker-compose.yml`, `Dockerfile`.

**Safety — this item touches user data.**

1. Ship the path change **read-new-fallback-old** for one release: if the new path has no DB and the legacy path does, read the legacy one and log a warning. Do not silently create an empty DB next to populated data.
2. Ship `scripts/migrate_data_dir.py` — copy (never move) legacy → `DATA_DIR`, verify row counts match, then print the manual `rm` command. Do not delete anything automatically.
3. Remove the fallback in the following release, not the same one.

**Verify.**
```bash
docker compose up -d
docker compose exec backend sh -c 'ls -la /app/data && test ! -d /app/src/reasoner/cache'
# then: create a run, docker compose down && up --build, confirm the run survives
```
The rebuild-survival check is the actual acceptance test. Everything else is a proxy.

**Rollback.** Revert; the legacy fallback means no data is stranded during the transition window.
**Size.** M

---

### F-03 · Production compose serves plaintext HTTP with no security headers

**Problem.** `docker-compose.yml:29` mounts `./Caddyfile` — the **development** one: `:80` only, no TLS, no HSTS, no CSP, no `X-Frame-Options`. Ports 80 and 443 are both published but nothing listens on 443. `Caddyfile.prod` exists but is an unfilled template (`yourdomain.com`, `your-email@example.com`) and sets `tls_insecure_skip_verify` on all four upstreams, which defeats the internal mTLS that F-01's cert-generator exists to provide.

**Evidence.** `VERIFIED` — both files read on `main`; compose mount confirmed.

**Approach.**
1. Parameterise the domain and ACME email via environment (`DOMAIN`, `ACME_EMAIL`), so `Caddyfile.prod` is deployable without editing a tracked file.
2. Make the compose file select the production Caddyfile, with the dev one used only via a `docker-compose.override.yml` (Compose's native mechanism for exactly this).
3. Remove `tls_insecure_skip_verify` and configure Caddy to trust the internal CA (`tls_trusted_ca_certs /certs/ca.crt`). Depends on F-01 producing real certs — sequence accordingly.
4. Add CSP. It is the one header in the project's own `rules/web/security.md` checklist that is missing from both Caddyfiles.

**Paradigm / Pattern.** **Convention over configuration via Compose overrides**, not two hand-maintained near-duplicate files. Two drifting copies of the same reverse-proxy config is precisely how the wrong one ended up mounted.

**Touches.** `docker-compose.yml`, new `docker-compose.override.yml`, `Caddyfile`, `Caddyfile.prod`.

**Verify.**
```bash
curl -sI https://$DOMAIN | grep -E 'strict-transport-security|content-security-policy|x-frame-options'
curl -sI http://$DOMAIN | head -1   # expect 308 → https
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
```
**Rollback.** Revert. Dependent on F-01; do not merge F-03 first.
**Size.** M

---

## 5. Phase 2 — Make the gates real

CI currently cannot fail. Fixing this before fixing the code is deliberate: without a ratchet, every subsequent phase can regress silently.

### F-04 · Lint and security gates are neutered

**Problem.** Nearly every quality step is suppressed.

**Evidence.** `VERIFIED` — read from the workflow files:

| Workflow | Step | Suppressor |
|---|---|---|
| `test.yml:33` | ruff (`B`, `F821`) | `--exit-zero` |
| `test.yml:37` | bandit | `--exit-zero` |
| `test.yml:41` | mypy | `\|\| true` |
| `security.yml:18` | pip-audit | `\|\| true` |
| `security.yml:19,20` | bandit | `\|\| true` |
| `security.yml:30` | npm audit | `\|\| true` |
| `self-healing-ci.yml:80,81,157` | coverage, `alembic check` | `\|\| true` |

Only `scripts/scan-secrets.py` is a real gate — and it passes (`VERIFIED`, clean on a fresh `main` checkout).

**Approach.** Remove every suppressor. Where the current state genuinely cannot pass, ratchet rather than suppress (§8.2). A gate that cannot fail is worse than no gate: it produces a green check that reviewers trust.

**Paradigm / Pattern.** **Fail-closed gates + ratcheting baseline.** The ratchet is the key move — it converts "we have 1552 whitespace warnings, so we disabled the linter" into "we have 1552, and 1553 fails the build." Stops the bleeding without a big-bang cleanup PR that nobody can review.

**Touches.** `.github/workflows/{test,security,coverage,self-healing-ci}.yml`, new `.quality-baseline.json`.
**Verify.** Introduce a deliberate `F821` in a scratch branch; CI must go red.
**Size.** S

---

### F-05 · The self-healing CI workflow does nothing on pull requests

**Problem.** The 26 KB `self-healing-ci.yml` is inert where it matters, and parts of it fabricate results.

**Evidence.** `VERIFIED` — read in full:

- Loops 1, 2, 3 and the SearXNG job all gate on `if: github.event_name == 'schedule' || github.event.inputs.healing_loop == ...`. On a `pull_request` both are false, so all four **skip**. Confirmed by `gh pr checks 7`, which reports `skipping` for each.
- The 60 %-fail coverage gate lives in Loop 1 — so it never runs on a PR.
- The only job that *does* run on a PR is `healing-profile`, whose every step ends in `|| true`. Its "baseline coverage" is measured from `pytest --collect-only` — that is import-time coverage, not execution coverage, and is meaningless. Its "documentation gap" check is `find . -name "*.md" | wc -l > 5`. Its "monitoring gap" check tests for `health_check.py` and `circuit_breaker.py` **at the repo root**, where neither has ever existed.
- Loop 2 generates smoke tests importing `ARAPipeline` (zero definitions in the repo — renamed to `ReasonerPipeline`), plus `health_check` and `retry_utils` modules that do not exist anywhere. It would fail immediately if it ever ran.
- Loop 3's three "reports" are hardcoded heredocs. `spec_drift_report.md` prints `Behavioral Drift: None detected` unconditionally. Counts (19, 8, 782) are literals. The heredoc delimiter is quoted, so even `$(date -Iseconds)` appears literally in the output.
- Phase 4 "Healing Verification" only `echo`s warnings, never exits non-zero, and writes `"status": "success"` regardless of loop results.
- The "Dead Man's Switch" writes `healing/heartbeat/latest.txt` on the ephemeral runner and never uploads or commits it. It monitors nothing.

**Approach.** Delete the workflow. Salvage the two genuinely useful pieces into honest jobs:

1. `healing/introspection_engine.py` — real static analysis. Move to a nightly `analysis.yml` that uploads its report as an artifact and **fails on P0 findings**.
2. The coverage gate — move into `coverage.yml`, where it will actually run on PRs.

Everything else is generated narrative. Deleting fabricated compliance artifacts is a security posture improvement, not merely cleanup: a report that always says "no drift detected" is worse than no report, because someone will eventually cite it.

**Paradigm / Pattern.** **Delete, don't refactor.** There is no core worth preserving; the value is concentrated in two steps that belong in existing workflows.

**Touches.** Delete `.github/workflows/self-healing-ci.yml`; new `.github/workflows/analysis.yml`; extend `coverage.yml`; update `CLAUDE.md` §7 and `AGENTS.md`, which both describe the healing loops as functioning infrastructure.
**Verify.** Open a draft PR; confirm the checks that appear are the ones that ran.
**Size.** M

---

### F-06 · Preset validator is not wired into CI, and 4 presets are broken

**Problem.** `scripts/validate_presets.py` exits 1 on `main` and is referenced by zero workflows.

**Evidence.** `VERIFIED`:
```
Validating 50 presets...
❌ 4 VALIDATION ERRORS:
  • pre-mortem-budget: unknown method 'pre_mortem'
  • pre-mortem-premium: unknown method 'pre_mortem'
  • self-discover-budget: unknown method 'self_discover'
  • self-discover-premium: unknown method 'self_discover'
```
`grep -c validate_presets .github/workflows/*.yml` → 0.

**Root cause.** Stringly-typed method identifiers with two competing conventions. `domain/preset_core.py:134-145` maps preset names to underscore methods (`pre_mortem`, `self_discover`); `:198-207` holds a reverse map back to hyphens; `scripts/validate_presets.py` hardcodes a hyphenated set. Three sources of truth for one concept. The same root cause produces the test failure `assert 'cross-language' == 'cross_language'` and `KeyError: 'cross_language'` in `test_cross_language.py`.

Note the validator itself may be the stale party — which of the two conventions the runtime honours was **not** determined. `HYPOTHESIS`: Pre-Mortem and Self-Discover presets fail method resolution at runtime, i.e. 2 of 19 advertised reasoning methods are broken end-to-end. **Confirm by running both presets before scoping the fix** — if they work, this is a validator bug (S); if they fail, it is a user-facing product defect (M).

**Approach.** Replace the stringly-typed identifiers with a single enum in the domain layer:

```python
# domain/methods.py — Domain layer
class ReasoningMethod(StrEnum):
    MULTI_PERSPECTIVE = "multi-perspective"
    PRE_MORTEM = "pre-mortem"
    SELF_DISCOVER = "self-discover"
    ...

    @property
    def module_suffix(self) -> str:      # "pre_mortem" — for module/attr lookup
        return self.value.replace("-", "_")
```

One canonical wire value (hyphenated, matching preset IDs and the UI), one derived Python identifier. Both mapping dicts in `preset_core.py` and the hardcoded set in the validator all become derivations of the enum.

**Paradigm / Pattern.** **Make illegal states unrepresentable.** A `str` method field admits 2^∞ invalid values and the codebase currently holds two spellings of two of them; a `StrEnum` admits exactly the 19 real ones and gives the type checker something to enforce. `StrEnum` specifically (not `Enum`) so existing serialization to SSE/JSON keeps working unchanged — this is a non-breaking wire-compatible change.

**Touches.** New `domain/methods.py`; `domain/preset_core.py`, `domain/preset_registry.py`, `scripts/validate_presets.py`, `application/flows/__init__.py` (flow registry lookup), `.github/workflows/test.yml`.
**Verify.** `python scripts/validate_presets.py` exits 0, wired as a required CI step. Add a test that every `ReasoningMethod` member resolves to a registered flow.
**Rollback.** Revert; enum is additive until call sites switch.
**Size.** M (S if the runtime turns out to honour the underscore form and only the validator is stale)

---

## 6. Phase 3 — Test suite triage

### F-07 · 125 failing tests, diffuse across 30+ files

**Problem.** 125 of 2,730 executed tests fail (4.6 %). No single dominant cause — the tail is long, which is harder to fix than a concentrated failure but also means each fix is small.

**Evidence.** `VERIFIED` — serial run, CI env vars, `-m "not slow and not integration"`: `125 failed, 2605 passed, 88 skipped, 505 deselected`. Top files: `test_multi_perspective_budget.py` (10), `test_openrouter.py` (9), `test_cross_language.py` (7), `test_bugfixes_regression.py` (7), `test_saas_quota_repo.py` (6), `test_ocr.py` (6).

Sampled root causes (`VERIFIED` via `--tb=line`):

| Category | Example | Fix |
|---|---|---|
| **Test rot — renamed symbols** | `PipelineState has no attribute 'perspectives'`; `PipelinePreset has no attribute 'build_router'`; `reasoner.uploader has no attribute '_extract_image'` | Update tests to current API |
| **Test rot — stale model IDs** | `Expected model 'gemini-flash' not found in registry`; `Unknown model ID: 'glm-5'` | Registry moved to `gemini-flash-lite` / `glm-5.2`. Tests assert retired IDs |
| **Naming drift** | `assert 'cross-language' == 'cross_language'`, `KeyError: 'cross_language'` | Fixed by F-06 |
| **Async mocking bugs** | `MagicMock can't be used in 'await' expression`; `'coroutine' object does not support the asynchronous context manager protocol` (all 6 in `test_saas_quota_repo.py`) | `AsyncMock` instead of `MagicMock` |
| **Environment** | `API key for 'deepseek-v3' is not set` | CI sets only `OPENROUTER_API_KEY`. Either add a dummy or mark the tests |
| **Needs triage** | `assert 403 == 500` ×3 in `test_bugfixes_regression.py`; `_ocr_scanned_pdf awaited 0 times` | `UNKNOWN` — could be real regressions |

**Approach.** Work file-by-file in descending failure count. Before fixing any test, decide explicitly: *is the test wrong, or is the code wrong?* Record the verdict in the commit message. The `403 == 500` and OCR cases must be resolved as code-or-test before the suite is declared green — those are the ones that could be masking real defects.

Two structural fixes worth making while in there:

1. **`AsyncMock` discipline.** The `MagicMock`-awaited failures are a recurring class. Add a shared `tests/fixtures/async_doubles.py` providing correctly-typed async doubles for the repository ports. **Pattern: Test Data Builder** — the brittleness comes from hand-rolling mock graphs per test.
2. **Drop `-n auto` from `pytest.ini` `addopts`.** `VERIFIED` — the suite crashes workers under xdist (`INTERNALERROR KeyError: <WorkerController gw8>`, `node down: Not properly terminated`, reproduced on both `main` and the removal branch, multiple runs, sometimes wedging near 97 %). Because it lives in `addopts`, *every* invocation inherits it including CI, so this is a live source of nondeterministic red builds. Move parallelism to an explicit CI flag and investigate the crashing test separately (`UNKNOWN` which one).

**Verify.** Compare **failure name sets** between branches, never counts — this session caught a real regression (`test_ask_web_search_action_returns_results`) that a count comparison would have hidden behind three unrelated removals.
```bash
diff <(sort before.txt) <(sort after.txt)
```
**Size.** L

---

### F-08 · Test collection depends on secrets, and markers are unregistered

**Problem.** `HYPOTHESIS` (branch-specific, verify on `main` after F-07 work). On the audited feature branch, three test files failed to *collect* without `JWT_SECRET_KEY` because `LocalAuthAdapter()` is instantiated at module import (`infrastructure/auth/local_adapter.py:38` raises on a short key). `main` collects cleanly, so this may already be resolved — but the underlying pattern (import-time side effects that raise) is the same one §2.2 exists to eliminate.

Separately `VERIFIED`: `pytest.mark.unit` was unregistered, producing `PytestUnknownMarkWarning` on every run. Already fixed on `chore/remove-searxng`.

**Approach.** Audit for module-level instantiation of anything that validates configuration. Convert to lazy factories or inject from the composition root (§2.2).
**Pattern.** **Lazy initialization / factory function** over module-level construction. Import must be a pure operation.
**Size.** S

---

## 7. Phase 4 — Supply chain and build reproducibility

### F-09 · Non-reproducible container builds

**Problem.** `Dockerfile:16` runs `pip install -r requirements.txt`, which pins version *ranges* (`fastapi>=0.109.0,<0.117.0`). A `requirements.lock` exists beside it and is unused.
**Evidence.** `VERIFIED` — file read; `docker build` succeeds (exit 0) but resolves fresh each time.
**Approach.** Install from `requirements.lock`. Keep `requirements.txt` as the human-authored input; regenerate the lock with `pip-compile` in a scheduled job that opens a PR. Add `--require-hashes` once the lock carries hashes.
**Pattern.** **Two-file dependency management** (abstract intent + concrete lock), the standard resolution for the "reproducible vs. maintainable" tension.
**Touches.** `Dockerfile`, `requirements.lock`, new `.github/workflows/deps.yml`.
**Verify.** Two builds a week apart produce identical `pip freeze` output.
**Size.** S

### F-10 · 9 high-severity npm vulnerabilities

**Evidence.** `VERIFIED` — `npm audit`: 9 high, 6 moderate, 1 low. High: `next` itself, `undici`, `ws`, `postcss`, `vite`, `sharp` (4 libvips CVEs), `js-yaml`, `brace-expansion`, `fast-uri`.
**Approach.** `npm audit fix` for the transitive ones; `next` needs a deliberate minor upgrade with a Playwright pass. Then wire `npm audit --audit-level=high` as a **failing** gate (currently `|| true`).
**Safety.** Upgrade `next` in its own PR. It is the framework; batching it with transitive fixes makes bisection impossible if the UI breaks.
**Verify.** `npm audit --audit-level=high` exits 0; `npx tsc --noEmit`, `npm run lint`, `npx playwright test` all pass.
**Size.** M

### F-11 · Python dependency CVEs unmeasured

**Problem.** `pip-audit` runs with `|| true` in CI, and could not be run locally (this environment's Python lacks the `venv` module). **No Python CVE data exists for this project.**
**Evidence.** `VERIFIED` that it is unmeasured; findings themselves `UNKNOWN`.
**Approach.** Run it, triage, then make it a failing gate.
**Size.** S to measure; `UNKNOWN` to remediate.

### F-12 · Package metadata is wrong

**Problem.** `pyproject.toml` declares `dependencies = []` despite ~40 real dependencies, and sets `build-backend = "setuptools.backends._legacy:_Backend"`, which is not a documented public backend.
**Evidence.** `VERIFIED` — file read.
**Approach.** Populate `dependencies` from `requirements.txt`; set `build-backend = "setuptools.build_meta"`. Also consolidate the duplicated pytest configuration — `pytest.ini` and `[tool.pytest.ini_options]` both exist with different `timeout` and `filterwarnings` values, and `pytest.ini` silently wins.
**Pattern.** **Single source of truth per concern.** Two config files for one tool is a latent trap.
**Size.** S

---

## 8. Phase 5 — Configuration, observability, health

### F-13 · Settings has no validation and no fail-fast

**Problem.** `core/settings.py` is a plain class whose attributes are `os.getenv(...)` calls evaluated at import. No types are enforced, no required-in-production invariants are checked, and a misconfigured production process starts happily and fails later at an arbitrary point. `CLAUDE.md` §3 describes it as pydantic-settings; it is not.
**Evidence.** `VERIFIED` — file read, 180+ lines of class-level `os.getenv`.

**Approach.**

```python
# core/settings.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", frozen=True)

    environment: Environment = Environment.DEVELOPMENT
    data_dir: Path = Path("./data")
    csrf_secret: SecretStr | None = None
    admin_api_key: SecretStr | None = None
    jwt_secret_key: SecretStr | None = None
    ...

    @model_validator(mode="after")
    def _enforce_production_invariants(self) -> Settings:
        if self.environment is not Environment.PRODUCTION:
            return self
        missing = [n for n in _REQUIRED_IN_PRODUCTION if getattr(self, n) is None]
        if missing:
            raise ValueError(f"Missing required production settings: {', '.join(missing)}")
        if self.cors_origins_list == _DEV_CORS_DEFAULT:
            raise ValueError("CORS_ORIGINS must be set explicitly in production")
        return self
```

**Paradigm / Pattern.** **Parse, don't validate** — the type of `Settings` should guarantee the invariants, so downstream code never re-checks `if settings.CSRF_SECRET`. `SecretStr` so credentials cannot land in a log line via `repr()` (defence in depth alongside the existing `redact_sensitive`). `frozen=True` because settings that mutate at runtime are untestable. Instantiated **at the composition root**, not at import — that is what makes F-08 tractable.

**Safety.** This will refuse to start currently-running deployments that are missing variables. That is the point, but it must not be a surprise. Ship in two steps: (1) validate and **log** violations for one release; (2) validate and **raise**. Announce between the two.

**Touches.** `core/settings.py`, `asgi.py`, `main.py`, every `from reasoner.core.settings import settings` call site (mechanical), `.env.example`, `DEPLOY.md`.
**Verify.** Unit tests asserting that a production environment with a missing `CSRF_SECRET` raises. Integration: container with an incomplete env exits non-zero with a clear message.
**Size.** L (call-site count is the cost, not the design)

---

### F-14 · Health endpoint conflates liveness and readiness, and does I/O per request

**Problem.** A single `/api/health` performs memory, circuit-breaker, cache, Postgres, Redis and Stripe checks. It **creates an asyncpg pool inside the request handler** on first call (`health.py:82-89`). There is no liveness/readiness distinction, so an orchestrator cannot tell "restart me" from "don't route to me yet." The `Dockerfile` `HEALTHCHECK` only asserts HTTP 200, so the container stays green while the body reports `"status": "unhealthy"`.

**Evidence.** `VERIFIED` — file read on `main`.

**Approach.** Split, and model each check as an object:

```python
# core/ports/health_port.py
class HealthCheck(Protocol):
    name: str
    critical: bool
    async def __call__(self) -> CheckResult: ...

# application/services/health_service.py
class CompositeHealthCheck:
    """Runs children concurrently; readiness = all critical children ok."""
```

- `GET /health/live` → process responsive. No dependencies. Never fails on a downstream outage.
- `GET /health/ready` → composite of `critical=True` checks. Drives load-balancer routing.
- `GET /api/health` → retained, full diagnostic detail, admin-gated (already correct today).

Connection pools move to the FastAPI `lifespan` handler.

**Paradigm / Pattern.** **Composite** — checks are uniform, compose into a tree, and the aggregate answers the same interface as a leaf. Adding a check becomes a registration, not an edit to a 100-line function. Concurrent execution via `asyncio.gather` bounds readiness latency to the slowest check rather than their sum.

**Touches.** `api/routes/health.py`, new `core/ports/health_port.py` and `application/services/health_service.py`, `Dockerfile`, `docker-compose.yml`, `Caddyfile*`.
**Verify.** `curl /health/live` stays 200 with Postgres stopped; `/health/ready` returns 503.
**Size.** M

---

### F-15 · Rate-limit rejection metrics are silently disabled

**Problem.** `infrastructure/rate_limiter.py:35` sets `_METRICS_AVAILABLE = False` unconditionally, with the metric import commented out at lines 37–40. The three `REASONER_RATE_LIMIT_REJECTED.labels(...).inc()` call sites at 219/226/241 are therefore dead. You have **zero observability on rate-limit rejections** — the signal you most need during an abuse event.

**Evidence.** `VERIFIED`. Note this is *not* a crash: `ruff` flags the three lines as `F821` undefined names, but the `if _METRICS_AVAILABLE:` guard means they are never evaluated. Correcting an earlier read in this session — there are **zero** runtime `NameError`s on `main`.

**Approach.** Restore the import. `infrastructure/metrics.py` already implements a correct **Null Object** (`_NoOpMetric` accepting `labels`/`inc`/`observe`/`set`) for when `prometheus_client` is absent, so the try/except guard is redundant — delete `_METRICS_AVAILABLE` entirely and call the metric unconditionally.
**Pattern.** **Null Object**, already present and correct. The bug is a local guard duplicating a responsibility the metrics module already discharges.
**Verify.** Trigger a 429; `curl /metrics | grep reasoner_rate_limit_rejected` shows a non-zero counter.
**Size.** S

---

## 9. Phase 6 — Data layer consolidation

### F-16 · Two migration systems

**Problem.** `migrations/001_saas_init.sql` … `006_call_telemetry.sql` (raw SQL) coexist with `migrations/alembic/versions/` (3 revisions including a baseline). No single source of truth for schema state. `alembic check` runs in CI with `|| true`, so drift is never detected.
**Evidence.** `VERIFIED` — directory listing and workflow read.
**Approach.** Alembic becomes canonical.
1. Verify the Alembic baseline (`df9629e72f17_baseline.py`) reflects the post-006 schema. If not, generate a corrective revision.
2. `alembic stamp head` against existing deployments.
3. Move `migrations/*.sql` to `migrations/legacy/` with a README stating they are historical and must not be applied.
4. Make `alembic check` a **failing** gate.

**Paradigm / Pattern.** **Expand/Contract (parallel change)** for all future schema work — add nullable column → backfill → switch reads → drop old. Mandatory once F-03 makes zero-downtime deploys possible.

**Safety — highest-risk item in this plan.**
- Never run against production without a verified `pg_dump` **and a tested restore**. An untested backup is not a backup.
- Rehearse the full sequence against a restored copy of production first.
- `alembic stamp` is metadata-only and does not touch data — but confirm the baseline matches reality before stamping, or the next `upgrade` will attempt to recreate existing objects.

**Verify.** On a restored production copy: `alembic current` → `head`, `alembic check` → clean, application boots and serves.
**Size.** M

### F-17 · No automated backups

**Problem.** `DEPLOY.md` documents manual `pg_dump`. Nothing is scheduled, and no restore has been tested.
**Evidence.** `VERIFIED` — repo-wide grep found only the manual documented commands.
**Approach.** Scheduled `pg_dump` sidecar to object storage, retention policy, and — non-negotiable — a **monthly automated restore test** into a scratch database that fails loudly if it does not complete.
**Verify.** Restore drill executes green on schedule.
**Size.** M
**Depends on.** F-02 (until the data directory is real, there is not much worth backing up beyond Postgres).

---

## 10. Phase 7 — Enhancements: xAI search integration

Researched this session against the official docs. Reasoner already whitelists `grok-4.5`, `grok-4.3` and `grok-build-0.1`, and already has direct-xAI routing when `XAI_API_KEY` is set (`infrastructure/llm/registry.py:91-95`, `:342-373`).

### E-01 · Architectural finding — these are not `SearchServicePort` backends

**Finding.** `VERIFIED` from the docs. xAI's `web_search` and `x_search` are **server-side** tools: Grok performs retrieval itself and returns synthesized prose with citations. Citations are URL-only — `{type: "url_citation", url, start_index, end_index, title}`, where `title` is the visible label ("1", "2"), not the page title. No snippets, no content, no publication dates.

`SearchServicePort.search()` (`core/ports/search_port.py:16`) returns `list[dict]` with `title/url/content/snippet/source/full_content`. Wrapping xAI behind it would require re-fetching every cited URL to reconstruct `content` — expensive, slow, and it discards the synthesis already paid for.

**Decision.** Introduce a second port rather than distorting the first.

```python
# core/ports/answer_engine_port.py — Core layer
class AnswerEnginePort(Protocol):
    """Retrieval + synthesis in one call. Returns prose plus citations,
    NOT a result list. Distinct from SearchServicePort by return shape."""
    async def answer(self, query: str, *, options: AnswerOptions) -> AnswerResult: ...
```

`AnswerResult` = `text: str` + `citations: list[Citation]`. Perplexity Sonar — already effectively this, currently squeezed through `PerplexitySearchClient` — becomes the second implementation. That refactor is worthwhile independently: it names a distinction the codebase already makes implicitly.

**Paradigm / Pattern.** **Interface Segregation.** Two genuinely different return contracts get two ports. The alternative — one port with optional fields — pushes `if result.content is None` checks into every consumer, which is exactly the impedance mismatch this avoids.
**Size.** M

### E-02 · `x_search` as the `social` source type

**Rationale.** Nothing in the stack can query X. Brave, Tavily and Perplexity all index the open web; X is substantially walled off. Concretely: breaking events (X leads the open web by hours), primary-source research via `from_date`/`to_date` + `allowed_x_handles`, and practitioner signal for the Delphi, Pre-Mortem and Brainstorming methods.

There is a direct gap to fill. `SourceType` already includes `"social"` (`core/ports/search_port.py:10`), and the only thing that ever serviced it was SearXNG's `"social media"` category mapping — **which the SearXNG removal deleted**. `x_search` fills a hole that work just opened, and fills it better.

**Parameters** (`VERIFIED`): `allowed_x_handles` / `excluded_x_handles` (max 20, mutually exclusive), `from_date` / `to_date` (ISO8601), `enable_image_understanding`, `enable_video_understanding`.
**Touches.** New `infrastructure/search/xai_answer_adapter.py`; register for `source_type="social"`.
**Size.** M

### E-03 · `web_search` on the HyperGate WEB_SEARCH route — and a hard capability guard

**Rationale.** The realtime path is currently single-vendor Perplexity. Cross-lab diversity is enforced everywhere else in the routing (≥3 labs in Phase 2 Budget; scorer from a different ecosystem than the dominant generator) — the realtime path is the one place the project's own stated principle is not applied.

**Parameters** (`VERIFIED`): `allowed_domains` / `excluded_domains` (max 5, mutually exclusive), `enable_image_understanding`, `enable_image_search`.

**The safety-critical part.** Server-side tools require the **direct xAI API**. `registry.py:342-373` routes `grok-*` through OpenRouter (`x-ai/grok-4.5`) unless `XAI_API_KEY` is set, and OpenRouter does not proxy provider server-side tools. A fallback to OpenRouter Grok would **silently drop the search capability while still returning a confident, fluent answer**. That is the worst possible failure mode for a system whose entire value proposition is epistemic honesty — an ungrounded answer indistinguishable from a grounded one.

**Approach.** Declare capabilities explicitly and check them in the router:

```python
# core/ports/llm_port.py
class Capability(StrEnum):
    SERVER_SIDE_WEB_SEARCH = "server_side_web_search"
    SERVER_SIDE_X_SEARCH = "server_side_x_search"

class LLMPort(Protocol):
    def supports(self, capability: Capability) -> bool: ...
```

`ProviderRouter` must exclude providers lacking a **required** capability from the fallback chain, and raise when the chain is exhausted. Never degrade silently.

**Paradigm / Pattern.** **Specification / capability declaration**, and a deliberate rejection of Null Object here — §2.3's boundary rule. Silent degradation is correct for a flaky perspective model; it is unacceptable for "did this answer touch the live web."

**Costs and unknowns.**
- `grok-4.5`: $2/$6 per M under 200k tokens, $4/$12 above, cached $0.30–0.60. Premium tier only — Budget presets target ~$0.02/run.
- `grok-4.3` is cheaper ($1.25/$2.50) and already whitelisted, but the docs list **only `grok-4.5`** as supporting these tools. `UNKNOWN` — verify before scoping a Budget tier.
- **The tools have no published price.** Perplexity, Brave and Tavily all have known per-query costs. `SPEND_CAP_PER_RUN_USD` cannot cap what it cannot price. Measure empirically against a small budget before enabling by default.

**Size.** M
**Depends on.** E-01.

---

## 11. Phase 8 — Hygiene

### F-18 · Repository clutter

**Evidence.** `VERIFIED` — ~130 loose files at the repo root, including `check_modules3.py`, `temp_read.py`, `find_greek.py`, `patch_silent.py`, `tmp_req.json`, `server_err.log`, 45 `.md` files, and a PDF. `docs/` holds 88 files, largely superseded plans and audits (`ARCH_AUDIT_REPORT_V2.md`, `ARCH-AUDIT-V2-REPORT.md`, `remediation-plan-v2-9.5.md`, …).
**Impact.** Not cosmetic. `scripts/scan-secrets.py` — the one real security gate — took over 5 minutes against the working tree and completed in seconds against a clean checkout. Clutter has a measurable cost on the security gate's usability.
**Approach.** Move scratch scripts to `scripts/scratch/` (gitignored) or delete. Archive superseded docs to `docs/archive/` with an index. Keep `docs/00X-*.md` ADRs — those are genuinely valuable and correctly formatted.
**Size.** S

### F-19 · Lint debt ratchet

**Evidence.** `VERIFIED` — 1552 `W293`, 1419 `E501`, 737 `F401`, 411 `I001`, 129 `E402`, 39 `F403` star-imports, 37 `F821`.
**Approach.** Do **not** attempt a big-bang cleanup; a 4,000-line whitespace diff is unreviewable and will bury real changes in the blame history. Instead:
1. Commit `.quality-baseline.json` with current per-rule counts.
2. CI fails if any count increases.
3. Auto-fix the safe rules (`W293`, `W291`, `I001`, `UP*`) in **one isolated PR** touching nothing else, and add that commit to `.git-blame-ignore-revs`.
4. Ratchet the baseline down opportunistically as files are touched for other reasons.
**Pattern.** **Ratchet / boy-scout rule**, mechanised. The 39 star-imports deserve priority — they are how undefined names hide from static analysis.
**Size.** M

### F-20 · Frontend tests never run in CI

**Evidence.** `VERIFIED` — 16 vitest files and a Playwright config exist; `test.yml` runs only `tsc --noEmit` and `eslint`.
**Approach.** Add `npm test` and a Playwright job. Playwright needs the backend, so gate it behind a compose-up step — which depends on F-01.
**Size.** S
**Depends on.** F-01.

### F-21 · Documentation truth

**Problem.** Several docs describe systems that do not work as written. `DEPLOY.md` states *"All inter-service communication uses mTLS"* — false while F-01 stands. `CLAUDE.md` §7 and `AGENTS.md` describe the self-healing loops as functioning infrastructure (F-05). `CLAUDE.md` §3 describes Settings as pydantic-settings (F-13). `CLAUDE.md` says 48 presets; the validator counts 50.
**Approach.** Update each as its underlying item lands — not before. Documentation describing intended-but-absent behaviour is worse than silence.
**Size.** S, distributed across other items.

---

## 12. Design decisions summarised

| Module | Paradigm / Pattern | Why this one |
|---|---|---|
| `core/paths.py` | Frozen Value Object + constructor injection | Ambient global path state *is* the F-02 bug. A singleton preserves it under a nicer name |
| `core/settings.py` | Parse-don't-validate; `BaseSettings`, frozen, `SecretStr` | Type guarantees invariants once, so no downstream re-checking. `SecretStr` keeps credentials out of `repr()` |
| `domain/methods.py` | `StrEnum` — make illegal states unrepresentable | Root cause of 4 broken presets + the `cross-language` failures is stringly-typed identifiers with two spellings. `StrEnum` keeps the wire format unchanged |
| `core/ports/answer_engine_port.py` | Interface Segregation | Retrieval and synthesis have genuinely different return contracts. One port with optional fields pushes `if x is None` into every consumer |
| Search backend selection | Strategy + Chain of Responsibility | Already implicit in `SEARCH_METHOD_CHAINS`; formalise rather than replace |
| Provider capabilities | Specification, **fail-loud** | Silent degradation is acceptable for a flaky perspective model, unacceptable for "did this answer touch the live web" |
| Health checks | Composite, concurrent | Uniform interface leaf-to-aggregate; adding a check becomes registration, not editing a 100-line function |
| Metrics | Null Object | Already correctly implemented in `infrastructure/metrics.py`; F-15 is a redundant local guard duplicating it |
| Migrations | Expand/Contract | Prerequisite for zero-downtime deploys once F-03 lands |
| Test doubles | Test Data Builder | The `MagicMock`-awaited failure class comes from hand-rolled per-test mock graphs |
| CI gates | Fail-closed + ratcheting baseline | Converts "too much debt, so we disabled it" into "this much, and no more" |
| Cert generation | Executable specification (script, not YAML scalar) | F-01 is the direct cost of embedding shell in a block scalar: unlintable, untestable, undiffable |

---

## 13. Sequencing

```
F-00 CI unblock ──┬─→ F-04 real gates ──→ F-19 lint ratchet
                  │                   └──→ F-06 preset enum ──→ F-07 test triage
                  └─→ F-05 delete healing CI

F-01 compose fix ──┬─→ F-03 TLS/headers ──→ F-17 backups
                   ├─→ F-20 playwright in CI
                   └─→ F-02 data paths ──→ F-16 migrations ──→ F-17 backups

F-13 settings ──→ F-08 import purity ──→ (unblocks F-07 tail)

F-09 lock ──→ F-11 pip-audit
F-10 npm ──→ (independent)
F-12 pyproject ──→ (independent)

F-14 health ──→ (independent, but pairs with F-03 for LB config)
F-15 metrics ──→ (independent, ship anytime)

E-01 answer port ──┬─→ E-02 x_search
                   └─→ E-03 web_search + capability guard
```

**Critical path:** F-00 → F-01 → F-02 → F-16. Everything else parallelises.

**Suggested order of merge.** F-00, F-15, F-12 (trivial, immediate) → F-01, F-04 (unblock deploy and gates) → F-02, F-03 → F-06, F-13 → F-07 (long tail, parallelise across engineers) → F-09/F-10/F-11 → F-14, F-16, F-17 → E-01/E-02/E-03 → F-18/F-19/F-20/F-21.

---

## 14. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| F-02 path change strands existing data | Medium | High | Read-new-fallback-old for one release; copy-never-move migration script; remove fallback only in the following release |
| F-16 migration consolidation corrupts production schema | Low | Critical | Verified `pg_dump` **with a tested restore**; full rehearsal against a restored copy; `stamp` is metadata-only but the baseline must be confirmed first |
| F-13 refuses to start existing deployments | High (by design) | Medium | Two-step rollout: log-only release, then enforce. Announce between |
| F-10 `next` upgrade breaks the UI | Medium | Medium | Isolated PR; Playwright pass; no batching with transitive fixes |
| F-07 "fixes" tests that were correctly failing | Medium | High | Every test change states test-wrong-or-code-wrong in the commit message. `403 == 500` and the OCR cases must be resolved as code-or-test before green is declared |
| E-03 silently returns ungrounded answers | Medium | **Critical** | Capability check raises rather than degrades. This is the reason E-03 has a hard guard rather than a fallback |
| xAI tool pricing unknown | High | Medium | Measure empirically against a small cap before enabling by default; do not ship to Budget tier until priced |
| Lint auto-fix PR buries real changes in blame | High | Low | Isolated PR; `.git-blame-ignore-revs` |
| xdist worker crashes produce nondeterministic CI red | Confirmed | Medium | Remove `-n auto` from `addopts` (F-07); investigate the crashing test separately |

---

## 15. Definition of done

Production-ready is claimed only when **all** hold:

1. `docker compose up -d` brings every service healthy from a clean checkout, with a real domain and TLS.
2. Application state survives `docker compose down && docker compose up --build`.
3. A production process with incomplete configuration **exits non-zero** with a specific message.
4. CI is green, and every gate can demonstrably fail — verified by deliberately breaking each one.
5. Test suite green, or every remaining failure is individually documented with a decision.
6. `pip-audit` and `npm audit --audit-level=high` both clean, both enforcing.
7. `alembic check` clean and enforcing; a restore drill has completed successfully.
8. `/health/live` and `/health/ready` behave correctly under a simulated dependency outage.
9. `python scripts/validate_presets.py` exits 0, wired into CI.
10. Every claim in `DEPLOY.md`, `CLAUDE.md` and `AGENTS.md` is true of the code as shipped.

---

## Appendix A — Reproducing the evidence

```bash
# Compose interpolation bug (F-01)
docker compose config | grep 'genrsa -out'

# Undefined names — all annotations, zero runtime (F-15 context)
python -m ruff check src/ --select F821 --output-format=concise

# Lint debt baseline (F-19)
python -m ruff check src/ --statistics

# Broken presets (F-06)
PYTHONPATH=src python scripts/validate_presets.py

# Test suite, matching CI markers and env (F-07)
JWT_SECRET_KEY=ci-test-secret-key-not-for-production-use-only \
CSRF_ENFORCE_BACKEND=false \
OPENROUTER_API_KEY=ci-dummy-openrouter-key-placeholder \
python -m pytest tests/ -q -n 0 -p no:randomly --tb=no -rf \
  -m "not slow and not integration" --timeout=45

# Failure-set comparison — NEVER compare counts (F-07)
diff <(grep '^FAILED' before.txt | sort) <(grep '^FAILED' after.txt | sort)

# Dependency audits (F-10, F-11)
cd ui-next && npm audit --audit-level=high
python -m pip_audit --requirement requirements.txt

# Secrets (currently clean)
python scripts/scan-secrets.py
```

## Appendix B — Items requiring investigation before scoping

| ID | Question | Why it matters |
|---|---|---|
| F-06 | Does the runtime honour `pre_mortem` or `pre-mortem`? | Determines whether 2 of 19 methods are broken for users (M) or only the validator is stale (S) |
| F-07 | Are the `assert 403 == 500` failures a real auth regression? | Could be masking a genuine security-relevant defect |
| F-07 | Which test crashes the xdist worker? | Source of nondeterministic CI failures |
| F-07 | Is the uploader `get_file_text` / `delete_file` failure real? | Possible live regression in upload retrieval and deletion |
| F-08 | Does `main` still have import-time config side effects? | Was branch-specific in the audit; verify before scoping |
| F-11 | What Python CVEs exist? | Completely unmeasured today |
| E-03 | Does `grok-4.3` support the server-side search tools? | Determines whether a Budget-tier xAI search preset is viable |
| E-03 | What do `web_search` / `x_search` cost per call? | `SPEND_CAP_PER_RUN_USD` cannot cap an unpriced call |
| — | Does `import-linter` pass on `main`? | Could not run locally: Windows `rich` conflict, `Only one live display may be active at once` |
