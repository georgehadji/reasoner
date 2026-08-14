#!/usr/bin/env bash
# Restore a dump produced by scripts/backup_db.sh.
#
# An untested backup is not a backup. Run this against a scratch database at
# least once before you need it — that is the whole point of --drill.
#
#   ./scripts/restore_db.sh --drill backups/reasoner-2026....dump
#       Restore into a temporary database, report the row counts, drop it.
#       Safe to run against production: it never touches the live database.
#
#   ./scripts/restore_db.sh --force backups/reasoner-2026....dump
#       Restore over the LIVE database. Destructive. Requires --force and a
#       typed confirmation.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-reasoner}"
DB_USER="${DB_USER:-postgres}"

MODE=""
DUMP=""
for arg in "$@"; do
  case "$arg" in
    --drill) MODE="drill" ;;
    --force) MODE="force" ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) DUMP="$arg" ;;
  esac
done

if [ -z "$MODE" ] || [ -z "$DUMP" ]; then
  echo "Usage: $0 --drill|--force <dump-file>" >&2
  exit 2
fi
if [ ! -s "$DUMP" ]; then
  echo "No such dump (or empty): $DUMP" >&2
  exit 1
fi

psql_q() {
  docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -tAc "$1" "${2:-postgres}"
}

if [ "$MODE" = "drill" ]; then
  SCRATCH="reasoner_restore_drill_$(date -u +%s)"
  echo "==> Drill: restoring into ${SCRATCH} (live database untouched)"
  psql_q "CREATE DATABASE ${SCRATCH};" >/dev/null

  # shellcheck disable=SC2317
  cleanup() {
    echo "==> Dropping ${SCRATCH}"
    psql_q "DROP DATABASE IF EXISTS ${SCRATCH};" >/dev/null || true
  }
  trap cleanup EXIT

  if ! docker compose exec -T "$DB_SERVICE" \
      pg_restore -U "$DB_USER" -d "$SCRATCH" --no-owner --no-acl /dev/stdin < "$DUMP"; then
    echo "FAIL: pg_restore reported errors — this dump is not restorable" >&2
    exit 1
  fi

  echo "==> Restored. Table row counts:"
  psql_q "SELECT relname || ': ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname;" "$SCRATCH"

  TABLES="$(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" "$SCRATCH")"
  if [ "${TABLES:-0}" -lt 1 ]; then
    echo "FAIL: restored database has no tables" >&2
    exit 1
  fi
  echo "==> Drill passed: ${TABLES} table(s) restored cleanly."
  exit 0
fi

echo "!!  This will REPLACE the live '${DB_NAME}' database with ${DUMP}."
echo "!!  Every row written since that dump will be lost."
printf 'Type the database name to confirm: '
read -r CONFIRM
if [ "$CONFIRM" != "$DB_NAME" ]; then
  echo "Aborted." >&2
  exit 1
fi

echo "==> Stopping backend so nothing writes mid-restore"
docker compose stop backend || true

echo "==> Restoring into ${DB_NAME}"
docker compose exec -T "$DB_SERVICE" \
  pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner --no-acl /dev/stdin < "$DUMP"

echo "==> Starting backend"
docker compose start backend

echo "==> Done. Check: curl -sf https://your-domain/api/health"
