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
#   bash scripts/ci-local.sh coverage   # coverage.yml (30% floor + domain/core floors)
#
# "coverage" is not in the default "all" run — it re-runs the full suite with
# --cov, which takes ~15-20min. Run it explicitly, or let coverage.yml run it
# in CI once Actions billing (Phase 0.1) is restored.
#
# Kept in sync by hand with .github/workflows/{test,pr-architecture,coverage}.yml.
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
    gate "ruff"   python scripts/ruff_ratchet.py --max 2239
    gate "bandit" bandit -r src/ -t B307,B308,B102 -f txt -q
    gate "mypy-strict-auth_legacy" mypy --strict src/reasoner/infrastructure/auth_legacy.py --ignore-missing-imports
    gate "mypy-ratchet" python scripts/mypy_ratchet.py --max 426
    gate "pytest" python -m pytest tests/ -m "not slow and not integration" \
        --tb=short --timeout=60 -q -p no:cacheprovider
fi

# ── architecture (pr-architecture.yml) ─────────────────────────────────
if want arch; then
    gate "import-linter"  lint-imports --no-cache
    gate "registry-guard" python scripts/check_no_registry_bypass.py
    gate "exception-count" python scripts/count_importlinter_exceptions.py --max 60
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

# ── coverage (coverage.yml) — explicit only, not part of "all" (slow) ──
if [ "$FILTER" = "coverage" ]; then
    gate "pytest-cov" python -m pytest tests/ -m "not slow and not integration" \
        --cov=src/reasoner --cov-report=xml --tb=short -q
    gate "coverage-floor" python -c "
import sys, xml.etree.ElementTree as ET
rate = float(ET.parse('coverage.xml').getroot().attrib.get('line-rate', 0)) * 100
print(f'Coverage: {rate:.1f}%')
sys.exit(0 if rate >= 30 else 1)
"
    gate "package-coverage-floor" python scripts/package_coverage_gate.py \
        --xml coverage.xml --package domain:85 --package core:75
fi

printf '\n════════ SUMMARY ════════\n%d passed, %d failed\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
    printf 'Failed gates: %s\n' "${FAILED_GATES[*]}"
    exit 1
fi
printf 'All gates green.\n'
