#!/usr/bin/env bash
# Local mirror of the GitHub Actions gates.
#
# GitHub-hosted runners are unavailable (Actions billing lapsed), so every
# check on a PR dies in ~3s without executing. This runs the same commands
# locally, with the same env, so a merge still has a real gate behind it.
#
#   bash scripts/ci-local.sh            # everything
#   bash scripts/ci-local.sh python     # ruff, bandit, mypy, pytest
#   bash scripts/ci-local.sh arch       # import-linter + registry guard
#   bash scripts/ci-local.sh frontend   # tsc, eslint, design tokens
#
# Kept in sync by hand with .github/workflows/{test,pr-architecture}.yml.
# If you change a gate there, change it here.
set -uo pipefail
cd "$(dirname "$0")/.."

FILTER="${1:-all}"
PASS=0; FAIL=0; FAILED_GATES=()

# test.yml sets these at the job level. They are not optional: without
# RATE_LIMITER_REDIS_FAILURE_MODE the limiter fails closed with no Redis and
# ~40 endpoint tests return 429; without JWT_SECRET_KEY auth adapters reject
# every token. Values are the CI placeholders, not real credentials.
export PYTHONPATH=src
export CSRF_ENFORCE_BACKEND=false
export OPENROUTER_API_KEY=ci-dummy-openrouter-key-placeholder
export JWT_SECRET_KEY=ci-test-secret-key-not-for-production-use-only
export RATE_LIMITER_REDIS_FAILURE_MODE=fail_open
export PYTHONIOENCODING=utf-8   # pytest crashes writing non-ASCII to cp1253

gate() {
    local name="$1"; shift
    printf '\n=== %s ===\n' "$name"
    if "$@"; then
        printf '  PASS: %s\n' "$name"; PASS=$((PASS + 1))
    else
        printf '  FAIL: %s\n' "$name"; FAIL=$((FAIL + 1)); FAILED_GATES+=("$name")
    fi
}

want() { [ "$FILTER" = "all" ] || [ "$FILTER" = "$1" ]; }

# ── python (test.yml: pytest job) ──────────────────────────────────────
if want python; then
    gate "ruff"   ruff check src/ --select B,F821 --ignore B008
    gate "bandit" bandit -r src/ -t B307,B308,B102 -f txt -q
    gate "mypy"   mypy --strict src/reasoner/infrastructure/auth_legacy.py --ignore-missing-imports
    gate "pytest" python -m pytest tests/ -m "not slow and not integration" \
        --tb=short --timeout=60 -q -p no:cacheprovider
fi

# ── architecture (pr-architecture.yml) ─────────────────────────────────
if want arch; then
    gate "import-linter"  lint-imports --no-cache
    gate "registry-guard" python scripts/check_no_registry_bypass.py
    gate "exception-count" bash -c '
        COUNT=$(grep -c "\->" .importlinter); MAX=65
        echo "import-linter exceptions: $COUNT (max $MAX)"
        [ "$COUNT" -le "$MAX" ]'
fi

# ── frontend (test.yml: tsc job) ───────────────────────────────────────
if want frontend; then
    gate "tsc"    bash -c 'cd ui-next && npx tsc --noEmit'
    gate "eslint" bash -c 'cd ui-next && npm run lint'
    # Inverted grep: any match is a violation.
    gate "design-tokens" bash -c '! grep -rEn --include=*.tsx --include=*.ts \
        --exclude=global-error.tsx \
        "(bg|text|border|from|to|via|ring|fill|stroke)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}" \
        ui-next/src'
fi

printf '\n════════ SUMMARY ════════\n%d passed, %d failed\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
    printf 'Failed gates: %s\n' "${FAILED_GATES[*]}"
    exit 1
fi
printf 'All gates green.\n'
