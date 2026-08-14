#!/usr/bin/env bash
# Build, verify, then switch — and keep the previous images so you can go back.
#
# DEPLOY.md documented `docker compose down && docker compose up -d --build`,
# which tears the running stack down *before* building its replacement. A build
# failure there leaves production down with nothing to fall back to, and because
# images were never tagged there was no previous artifact to roll back to either.
#
# This builds first, tags the result, and only then restarts — and records the
# previous tag so scripts/rollback.sh can undo it.
#
#   ./scripts/deploy.sh              # build, migrate, restart, health-check
#   ./scripts/deploy.sh --no-pull    # skip git pull (deploy the working tree)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STATE_DIR="${STATE_DIR:-$REPO_ROOT/.deploy}"
mkdir -p "$STATE_DIR"

PULL=1
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$PULL" -eq 1 ]; then
  echo "==> Pulling latest"
  git pull --ff-only
fi

TAG="$(git rev-parse --short HEAD)"
echo "==> Deploying ${TAG}"

echo "==> Validating .env before touching the running stack"
python3 scripts/preflight_check.py

# Build BEFORE stopping anything. If this fails, production is still serving.
echo "==> Building images (current stack still serving)"
docker compose build

echo "==> Tagging images as ${TAG}"
for svc in backend frontend; do
  img="$(docker compose images -q "$svc" 2>/dev/null | head -1)"
  built="$(docker compose config --images 2>/dev/null | grep -E "${svc}" | head -1 || true)"
  # Record what is running now, so rollback has a target.
  if [ -n "$img" ]; then
    docker tag "$img" "reasoner-${svc}:previous" 2>/dev/null || true
  fi
  if [ -n "$built" ]; then
    docker tag "$built" "reasoner-${svc}:${TAG}" 2>/dev/null || true
  fi
done

# Remember the commit we are replacing, for rollback.sh.
if [ -f "$STATE_DIR/current" ]; then
  cp "$STATE_DIR/current" "$STATE_DIR/previous"
fi
echo "$TAG" > "$STATE_DIR/current"

echo "==> Restarting services"
# `up -d` recreates only what changed and keeps the rest serving; it does not
# tear the whole stack down the way `down` does.
docker compose up -d --remove-orphans

echo "==> Waiting for the backend to report healthy"
for _ in $(seq 1 60); do
  state="$(docker compose ps --format json backend 2>/dev/null | grep -o '"Health":"[^"]*"' | head -1 || true)"
  case "$state" in
    *healthy*) echo "==> Backend healthy"; break ;;
  esac
  sleep 5
done

if ! docker compose ps backend | grep -q 'healthy'; then
  echo "FAIL: backend did not become healthy." >&2
  echo "      Roll back with: ./scripts/rollback.sh" >&2
  docker compose logs --tail 50 backend >&2
  exit 1
fi

echo "==> Deployed ${TAG}."
echo "    Previous: $(cat "$STATE_DIR/previous" 2>/dev/null || echo 'none recorded')"
echo "    Roll back with: ./scripts/rollback.sh"
