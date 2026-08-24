# Pre-Existing CI Failure Fix Plan

**Date:** 2026-08-22
**Branch:** main (commit d6a475ca)
**Status:** All 13 CI checks failing on main

---

## Executive Summary

Every CI check on `main` is currently red. The failures cluster into **5 root causes** that, once fixed in dependency order, should restore the entire pipeline to green. The plan respects Reasoner's hexagonal DDD architecture — fixes stay in the correct layer, no new architectural violations are introduced.

---

## Root Cause Analysis

### RC-1: Frontend TypeScript Compilation (3,815 errors)

**Affected CI jobs:** `tsc` (TypeScript type check), `frontend` (npm audit)

**Root cause:** `npm ci` in CI installs dependencies from `package-lock.json`, but the React 19 / Next.js 16 type ecosystem requires `@types/react` to provide `JSX.IntrinsicElements`. The installed `@types/react` package is missing its `jsx-runtime.d.ts`, causing 3,121 TS7026 errors ("JSX element implicitly has type 'any' because no interface 'JSX.IntrinsicElements' exists"). Additional errors:

| Error Code | Count | Description |
|-----------|-------|-------------|
| TS7026 | 3,121 | Missing JSX.IntrinsicElements (root cause: @types/react version) |
| TS2307 | 254 | Cannot find module (missing dev dependencies: vitest, @playwright/test, @sentry/nextjs) |
| TS7006 | 171 | Parameter implicitly has 'any' type (app-store.ts Zustand callbacks) |
| TS2875 | 84 | Module path 'react/jsx-runtime' not found |
| TS2591 | 58 | Cannot find name (missing @types/node) |
| TS7031 | 45 | Binding element implicitly has 'any' type |

**Files with most errors:** `ChatFeed.tsx` (166), `RunRecord.tsx` (163), `LandingPage.tsx` (135), `api-keys/page.tsx` (126), `PhaseRenderer.tsx` (120)

### RC-2: npm Audit Vulnerabilities

**Affected CI jobs:** `frontend` (npm audit --audit-level high), `sbom-and-image-scan` (Trivy)

**Root cause:** 4 high-severity vulnerabilities in `ui-next/node_modules`, primarily in `sharp` and potentially in transitive dependencies from Next.js 16.

### RC-3: Missing `requirements.lock.txt`

**Affected CI jobs:** `lockfile-freshness`

**Root cause:** The file `requirements.lock.txt` does not exist in the repository. The CI job runs `scripts/lock_requirements.sh` (pip-compile with `--generate-hashes`) and diffs the result against the committed file. No committed file = immediate failure.

### RC-4: pip-audit / Trivy Dependency Vulnerabilities

**Affected CI jobs:** `python` (pip-audit), `sbom-and-image-scan` (Trivy filesystem scan)

**Root cause:** `pip-audit` checks `requirements.txt` against the PyPI advisory database. With 100+ Python dependencies, it's likely that at least one has a known CRITICAL/HIGH CVE. Trivy independently scans the same dependency tree.

### RC-5: Self-Healing CI Jobs

**Affected CI jobs:** `Generate Healing Profile`, `Phase 4 - Healing Verification`

**Root cause:** The `self-healing-ci.yml` workflow's `healing-profile` job runs on every push/PR. It collects baseline coverage by running pytest — if pytest itself fails (due to any of the above), the healing profile generation fails, which cascades to `healing-verification` (runs with `if: always()`).

---

## Fix Plan (Dependency-Ordered)

### Phase 1: Python Backend (unblocks RC-3, RC-4, RC-5)

#### Fix 1.1: Generate and commit `requirements.lock.txt`

**Layer:** Infrastructure (build tooling)
**Effort:** 5 minutes
**Risk:** Low

```bash
bash scripts/lock_requirements.sh
git add requirements.lock.txt
git commit -m "chore: generate initial requirements.lock.txt for CI lockfile-freshness check"
```

This unblocks the `lockfile-freshness` CI job. Going forward, any change to `requirements.txt` must be followed by re-running this script.

#### Fix 1.2: Resolve pip-audit findings

**Layer:** Infrastructure (dependencies)
**Effort:** 30–60 minutes
**Risk:** Medium (dependency upgrades may break imports)

Steps:
1. Install `pip-audit`: `pip install pip-audit`
2. Run `pip-audit -r requirements.txt` to list all CVEs
3. For each finding:
   - If a patched version exists and is compatible: bump the pin in `requirements.txt`
   - If no patch exists: add to `pip-audit`'s known-exploits exclusion list (`.pip-audit-known-vulnerabilities`) with a comment explaining why
4. Re-run `scripts/lock_requirements.sh` after any `requirements.txt` change
5. Verify with `pip-audit -r requirements.txt` → clean

**Architecture note:** Only `requirements.txt` is touched. No source code changes. The lockfile must be regenerated after every change.

#### Fix 1.3: Verify pytest passes on Python 3.12

**Layer:** Application (agent_results.py) + Tests
**Effort:** 15 minutes
**Risk:** Low

The `mappingproxy` dataclass default in `agent_results.py:149` works on Python 3.12 (CI's version) but fails on 3.11. While this doesn't block CI, it blocks local development on 3.11. Fix for broader compatibility:

```python
# Before (line 164):
claim_labels: Mapping[str, str] = types.MappingProxyType({})
total_tokens: Mapping[str, int] = types.MappingProxyType(
    {"input": 0, "output": 0, "total": 0}
)

# After:
claim_labels: Mapping[str, str] = field(default_factory=lambda: types.MappingProxyType({}))
total_tokens: Mapping[str, int] = field(
    default_factory=lambda: types.MappingProxyType({"input": 0, "output": 0, "total": 0})
)
```

This preserves the `frozen=True` immutability guarantee while being compatible with Python 3.11+.

**Additional test fix** — `tests/test_bug004_parsing_truncated_json.py:31` has a PEP 701 f-string (nested quotes inside f-string) that is valid only on Python 3.12+:

```python
# Before (line 31):
f"got {result.count('"')} in {result!r}"

# After:
f'got {result.count(chr(34))} in {result!r}'
# Or:
f"got {result.count('\"')} in {{result!r}}"
# Or simply:
f"got {quote_count} in {result!r}"  # with quote_count = result.count('"')
```

#### Fix 1.4: Run full pytest suite and fix any assertion failures

**Layer:** Various (tests)
**Effort:** 1–3 hours (depends on number of genuine failures)
**Risk:** Medium

Once the collection errors are resolved, run the full suite with CI-equivalent environment:

```bash
PYTHONPATH=src \
CSRF_ENFORCE_BACKEND=false \
OPENROUTER_API_KEY=ci-dummy-openrouter-key-placeholder \
JWT_SECRET_KEY=ci-test-secret-key-not-for-production-use-only \
RATE_LIMITER_REDIS_FAILURE_MODE=fail_open \
python -m pytest tests/ -v -m "not slow and not integration" --timeout=60 -q
```

Fix failures in priority order:
1. Import errors (missing modules, circular imports)
2. Fixture errors (missing fixtures, wrong signatures)
3. Assertion failures (tests that need updating for current behavior)
4. Timeout failures (tests that take >60s)

### Phase 2: Frontend TypeScript (unblocks RC-1, RC-2)

#### Fix 2.1: Fix React/Next.js type resolution

**Layer:** Interface (ui-next)
**Effort:** 30–60 minutes
**Risk:** Medium

The 3,121 TS7026 errors stem from a broken `@types/react` installation. Steps:

1. **Verify `package-lock.json` integrity:**
   ```bash
   cd ui-next
   rm -rf node_modules
   npm ci
   npx tsc --noEmit 2>&1 | grep -c "error TS"
   ```

2. **If errors persist with clean install**, the issue is in dependency resolution:
   - Check that `@types/react` version matches the React 19 types (`npm ls @types/react`)
   - Ensure `tsconfig.json` has correct `jsx: "react-jsx"` (it does)
   - For React 19, types are bundled with `react` itself — `@types/react@^19` may need to be `@types/react@19.x.x` (exact match)

3. **If `package-lock.json` is stale**, regenerate:
   ```bash
   rm package-lock.json
   npm install
   npx tsc --noEmit
   ```
   Commit the updated `package-lock.json`.

4. **Fix remaining TS7006 errors** in `app-store.ts` (15 instances):
   These are genuine type-safety issues — Zustand `set()` callbacks lack parameter types. Add explicit types:
   ```typescript
   // Before:
   set((state) => { ... })
   // After:
   set((state: AppState) => { ... })
   ```

5. **Exclude test/config files from tsc** if they require dev dependencies not in the main tsconfig:
   Add to `tsconfig.json`:
   ```json
   "exclude": ["src/test/**", "vitest.config.ts", "playwright.config.ts", "e2e/**"]
   ```
   Or install the missing dev type dependencies.

#### Fix 2.2: Resolve npm audit vulnerabilities

**Layer:** Interface (ui-next dependencies)
**Effort:** 15–30 minutes
**Risk:** Low–Medium

```bash
cd ui-next
npm audit --audit-level high
npm audit fix
```

If `npm audit fix` doesn't resolve all high-severity issues:
- Check if `sharp` can be updated: `npm install sharp@latest`
- For vulnerabilities in transitive dependencies with no fix available, document in a `.nsprc` or `audit-exceptions.json`

#### Fix 2.3: Design token guard compliance

**Layer:** Interface (ui-next components)
**Effort:** 15 minutes
**Risk:** Low

The design token guard greps for raw Tailwind palette colors (e.g., `bg-slate-500`). Verify:
```bash
grep -rEn --include=*.tsx --include=*.ts \
  --exclude=global-error.tsx \
  '(bg|text|border|from|to|via|ring|fill|stroke)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}' \
  src
```

Replace any matches with CSS custom property equivalents defined in `globals.css`.

### Phase 3: SDK (likely already green)

#### Fix 3.1: Verify SDK type check and tests

**Layer:** Interface (sdk/typescript)
**Effort:** 5 minutes
**Risk:** Low

The SDK type check (`npx tsc --noEmit -p tsconfig.build.json`) passed locally. Verify:
```bash
cd sdk/typescript
npm ci
npx tsc --noEmit -p tsconfig.build.json
npm test
```

If tests fail, they likely involve SDK contract drift — the backend's SSE event shapes have changed without updating the SDK's type definitions. Fix by updating `sdk/typescript/src/types.ts` to match current backend event schemas in `src/reasoner/api/schemas.py` and `src/reasoner/api/serializers.py`.

### Phase 4: Security Scans

#### Fix 4.1: Trivy filesystem and config scans

**Layer:** Infrastructure (Docker, dependencies)
**Effort:** 30 minutes
**Risk:** Low

Trivy scans for CRITICAL/HIGH CVEs in the dependency tree and Dockerfile misconfigurations. After fixing pip-audit (1.2) and npm audit (2.2), Trivy should largely pass. Remaining issues:

1. **Dockerfile misconfigs:** Review `Dockerfile` and `docker-compose*.yml` for:
   - Running as root (add `USER` directive)
   - Missing health checks
   - Exposed secrets in build args

2. **Residual CVEs:** If Trivy finds CVEs that pip-audit/npm-audit missed, create a `.trivyignore` for unfixed findings with comments.

#### Fix 4.2: Secret scanner

**Layer:** Infrastructure (scripts)
**Effort:** 5 minutes
**Risk:** Low

`scripts/scan-secrets.py` regex-scans for hardcoded API keys. Verify:
```bash
python scripts/scan-secrets.py
```

If false positives arise from test fixtures or example configs, add them to the scanner's exclusion list.

### Phase 5: Self-Healing CI (auto-resolves)

#### Fix 5.1: Healing profile and verification

**Layer:** Infrastructure (CI/CD)
**Effort:** 0 minutes (auto-resolves)
**Risk:** None

The `healing-profile` job runs pytest for baseline coverage. Once pytest passes (Phase 1), this job will auto-resolve. The `healing-verification` job validates artifacts from the healing loops — since the loops use `|| true` liberally, they mostly pass; the verification job will pass once `healing-profile` succeeds.

---

## Implementation Order

```
Phase 1.1  ─── Generate requirements.lock.txt
    │
Phase 1.2  ─── Fix pip-audit CVEs + regenerate lockfile
    │
Phase 1.3  ─── Fix agent_results.py mappingproxy + test_bug004 f-string
    │
Phase 1.4  ─── Run & fix pytest suite ────────────────┐
    │                                                  │
Phase 2.1  ─── Fix TS type resolution (parallel) ─────┤
    │                                                  │
Phase 2.2  ─── Fix npm audit vulns ───────────────────┤
    │                                                  │
Phase 2.3  ─── Design token guard ────────────────────┤
    │                                                  │
Phase 3.1  ─── Verify SDK (parallel) ─────────────────┤
    │                                                  │
Phase 4.1  ─── Trivy scans ──────────────────────────┤
    │                                                  │
Phase 4.2  ─── Secret scanner ────────────────────────┘
    │
Phase 5.1  ─── (auto-resolves when 1.4 passes)
```

Phases 1.1–1.3 are sequential (each depends on the prior). After 1.3, Phases 1.4, 2.x, 3.x, and 4.x can proceed in parallel. Phase 5 auto-resolves.

---

## Estimated Total Effort

| Phase | Effort | Risk |
|-------|--------|------|
| 1.1 Lockfile | 5 min | Low |
| 1.2 pip-audit | 30–60 min | Medium |
| 1.3 Compat fixes | 15 min | Low |
| 1.4 Pytest fixes | 1–3 hrs | Medium |
| 2.1 TS types | 30–60 min | Medium |
| 2.2 npm audit | 15–30 min | Low |
| 2.3 Design tokens | 15 min | Low |
| 3.1 SDK verify | 5 min | Low |
| 4.1 Trivy | 30 min | Low |
| 4.2 Secrets | 5 min | Low |
| **Total** | **3–6 hours** | |

---

## Verification Checklist

After all fixes, run the full local CI mirror:

```bash
# Python
bash scripts/ci-local.sh python

# Architecture
bash scripts/ci-local.sh arch

# Frontend
bash scripts/ci-local.sh frontend

# Or all at once:
bash scripts/ci-local.sh all
```

Then push to a branch and verify all 13 GitHub Actions checks pass.

---

## Architectural Notes

- **No new `ignore_imports` entries:** Current count is 60 (max 65). Fixes must not add cross-layer imports.
- **No `tailwind.config.ts`:** Tailwind v4 is CSS-native. Config lives in `globals.css`.
- **Hexagonal boundaries:** Dependency fixes stay in `requirements.txt`/`package.json` (infrastructure). Code fixes in `agent_results.py` stay in the application layer. Test fixes stay in `tests/`.
- **CQRS compliance:** No changes to command/query handlers needed for CI fixes.
- **Port/adapter integrity:** The `mappingproxy` fix in `agent_results.py` preserves the `frozen=True` immutability contract — `default_factory` wrapping is the standard Python pattern for this.
