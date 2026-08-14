#!/usr/bin/env bash
# Run every CI gate locally, in the same order and with the same commands the
# workflows use.
#
# GitHub Actions is not always available — a private repo that runs out of
# billed minutes fails every job in ~2s with no runner assigned, which looks
# identical to a code failure but tells you nothing. This script reproduces the
# gates on your own machine so a green pipeline can be established without
# depending on the runner pool.
#
#   ./scripts/verify_ci.sh              # every gate
#   ./scripts/verify_ci.sh --backend    # skip the frontend gates (no Node needed)
#   ./scripts/verify_ci.sh --fast       # skip the coverage re-run (slowest gate)
#
# Exit code 0 means every blocking gate passed.
#
# Sources: .github/workflows/{test,coverage,pr-architecture,security}.yml

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
RUN_FRONTEND=1
RUN_COVERAGE=1

for arg in "$@"; do
  case "$arg" in
    --backend) RUN_FRONTEND=0 ;;
    --fast)    RUN_COVERAGE=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# The pytest job sets these; without them provider construction and auth test
# collection raise, and the Redis-backed limiter denies every request.
export PYTHONPATH=src
export CSRF_ENFORCE_BACKEND=false
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-ci-dummy-openrouter-key-placeholder}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-ci-test-secret-key-not-for-production-use-only}"
export RATE_LIMITER_REDIS_FAILURE_MODE=fail_open

FAILED=()
PASSED=()
SKIPPED=()

blue()  { printf '\n\033[1;34m=== %s\033[0m\n' "$1"; }
green() { printf '\033[0;32mPASS\033[0m  %s\n' "$1"; }
red()   { printf '\033[0;31mFAIL\033[0m  %s\n' "$1"; }
grey()  { printf '\033[0;90mSKIP\033[0m  %s\n' "$1"; }

# gate <name> <command...> — a blocking gate; a non-zero exit fails the script.
gate() {
  local name="$1"; shift
  blue "$name"
  if "$@"; then
    green "$name"; PASSED+=("$name")
  else
    red "$name"; FAILED+=("$name")
  fi
}

# advisory <name> <command...> — mirrors a CI step that uses --exit-zero or
# `|| true`, so it reports but never blocks.
advisory() {
  local name="$1"; shift
  blue "$name (advisory)"
  "$@" || true
  grey "$name — informational, does not block"
  SKIPPED+=("$name (advisory)")
}

need() {
  command -v "$1" >/dev/null 2>&1 || {
    grey "$2 — $1 not found"; SKIPPED+=("$2 (missing $1)"); return 1
  }
}

# ── Test / pr-architecture / security workflows ──────────────────────────────

advisory "ruff (B-rules + undefined names)" \
  "$PYTHON" -m ruff check src/ --select B,F821 --ignore B008

advisory "bandit" \
  "$PYTHON" -m bandit -r src/ -t B307,B308,B102 -f txt

gate "secret scan" "$PYTHON" scripts/scan-secrets.py

gate "pytest (unit + integration)" \
  "$PYTHON" -m pytest tests/ -m "not slow and not integration" --tb=short --timeout=60 -q

if need lint-imports "import-linter"; then
  gate "import-linter" lint-imports --no-cache
fi

check_import_ratchet() {
  local count max=65
  count=$(grep -c '\->' .importlinter)
  echo "Import-linter exceptions: $count (max $max)"
  [ "$count" -le "$max" ]
}
gate "import-linter exception ratchet" check_import_ratchet

# ── Coverage workflow ────────────────────────────────────────────────────────

run_coverage() {
  "$PYTHON" -m pytest tests/ -m "not slow and not integration" \
    --cov=src/reasoner --cov-report=xml --tb=short -q || return 1
  local cov
  cov=$("$PYTHON" -c "
import xml.etree.ElementTree as ET
print(f\"{float(ET.parse('coverage.xml').getroot().attrib.get('line-rate', 0)) * 100:.1f}\")
")
  echo "Coverage: ${cov}%"
  "$PYTHON" -c "
cov = float('${cov}')
if cov < 30:
    print(f'FAIL: Coverage {cov:.1f}% is below the 30% hard floor'); exit(1)
elif cov < 80:
    print(f'WARN: Coverage {cov:.1f}% is below the 80% target')
else:
    print(f'OK: Coverage {cov:.1f}% meets target')
"
}

if [ "$RUN_COVERAGE" -eq 1 ]; then
  gate "coverage gate" run_coverage
  rm -f coverage.xml .coverage
else
  grey "coverage gate — skipped (--fast)"; SKIPPED+=("coverage gate (--fast)")
fi

# ── Frontend gates ───────────────────────────────────────────────────────────

if [ "$RUN_FRONTEND" -eq 1 ]; then
  if need npm "frontend gates"; then
    [ -d ui-next/node_modules ] || (cd ui-next && npm ci)
    gate "TypeScript type check" bash -c "cd ui-next && npx tsc --noEmit"
    gate "eslint"                bash -c "cd ui-next && npm run lint"
    gate "next build"            bash -c "cd ui-next && npm run build"
  fi
else
  grey "frontend gates — skipped (--backend)"; SKIPPED+=("frontend gates (--backend)")
fi

# ── Summary ──────────────────────────────────────────────────────────────────

blue "Summary"
for name in "${PASSED[@]:-}";  do [ -n "$name" ] && green "$name"; done
for name in "${SKIPPED[@]:-}"; do [ -n "$name" ] && grey  "$name"; done
for name in "${FAILED[@]:-}";  do [ -n "$name" ] && red   "$name"; done

if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n%d blocking gate(s) failed.\n' "${#FAILED[@]}"
  exit 1
fi

printf '\nAll blocking gates passed.\n'
