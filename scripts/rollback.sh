#!/usr/bin/env bash
# Return to the previously deployed commit.
#
# There was no rollback path at all: the deploy procedure never tagged images, so
# a bad deploy could only be fixed by rolling forward. scripts/deploy.sh records
# each deployed commit under .deploy/, and this checks it back out and rebuilds.
#
#   ./scripts/rollback.sh              # back to the previous deploy
#   ./scripts/rollback.sh <commit>     # back to a specific commit
#
# Note on the database: this rolls back CODE only. If the deploy you are undoing
# applied a migration, roll that back deliberately — `alembic downgrade -1` — or
# restore from a dump with scripts/restore_db.sh. Rolling code back under a newer
# schema is usually fine, but never assume it.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STATE_DIR="${STATE_DIR:-$REPO_ROOT/.deploy}"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  if [ ! -f "$STATE_DIR/previous" ]; then
    echo "No previous deploy recorded in ${STATE_DIR}/previous." >&2
    echo "Pass a commit explicitly: ./scripts/rollback.sh <commit>" >&2
    exit 1
  fi
  TARGET="$(cat "$STATE_DIR/previous")"
fi

if ! git rev-parse --verify "$TARGET^{commit}" >/dev/null 2>&1; then
  echo "Not a commit in this repository: ${TARGET}" >&2
  exit 1
fi

CURRENT="$(git rev-parse --short HEAD)"
echo "!!  Rolling back from ${CURRENT} to ${TARGET}."
echo "!!  Code only — migrations applied since ${TARGET} stay applied."
printf 'Continue? [y/N] '
read -r CONFIRM
case "$CONFIRM" in
  y|Y|yes|YES) ;;
  *) echo "Aborted."; exit 1 ;;
esac

echo "==> Checking out ${TARGET}"
git checkout --detach "$TARGET"

echo "==> Rebuilding (current stack still serving)"
docker compose build

echo "==> Restarting"
docker compose up -d --remove-orphans

echo "==> Waiting for the backend to report healthy"
for _ in $(seq 1 60); do
  if docker compose ps backend | grep -q 'healthy'; then
    echo "==> Backend healthy"
    break
  fi
  sleep 5
done

if ! docker compose ps backend | grep -q 'healthy'; then
  echo "FAIL: backend still unhealthy after rollback." >&2
  docker compose logs --tail 50 backend >&2
  exit 1
fi

echo "$TARGET" > "$STATE_DIR/current"
echo "==> Rolled back to ${TARGET}."
echo "    You are on a detached HEAD. To resume normal work: git checkout main"
