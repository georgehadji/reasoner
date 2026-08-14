#!/usr/bin/env bash
# Dump the production Postgres database, verify the dump, prune old ones, and
# optionally copy off-box.
#
# Backups existed only as a pg_dump line in DEPLOY.md — nothing scheduled, and no
# restore ever tested. This is the scheduled half; scripts/restore_db.sh is the
# other half, and you should run it against a throwaway database before you rely
# on any of this.
#
#   ./scripts/backup_db.sh                    # dump to ./backups
#   BACKUP_DIR=/mnt/vol ./scripts/backup_db.sh
#   BACKUP_REMOTE="s3://bucket/reasoner" ./scripts/backup_db.sh   # needs aws cli
#
# Install as a nightly cron on the host (03:30, keeping the container out of it):
#   30 3 * * * cd /srv/reasoner && ./scripts/backup_db.sh >> /var/log/reasoner-backup.log 2>&1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
DB_SERVICE="${DB_SERVICE:-postgres}"
DB_NAME="${DB_NAME:-reasoner}"
DB_USER="${DB_USER:-postgres}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"

# A dump named for a timestamp we control, so restores are unambiguous.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/reasoner-${STAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "==> Dumping ${DB_NAME} to ${OUT}"
# -Fc (custom format) so restore can be selective and parallel, unlike plain SQL.
docker compose exec -T "$DB_SERVICE" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc --no-owner --no-acl \
  > "$OUT"

if [ ! -s "$OUT" ]; then
  echo "FAIL: dump is empty — refusing to keep it" >&2
  rm -f "$OUT"
  exit 1
fi

# A dump that cannot be listed cannot be restored. Catch corruption now, while
# the database is still healthy, rather than during an incident.
echo "==> Verifying dump is readable"
if ! docker compose exec -T "$DB_SERVICE" pg_restore --list /dev/stdin < "$OUT" > /dev/null 2>&1; then
  echo "FAIL: pg_restore could not read the dump — treating as corrupt" >&2
  mv "$OUT" "$OUT.corrupt"
  exit 1
fi

SIZE="$(du -h "$OUT" | cut -f1)"
echo "==> OK: ${OUT} (${SIZE})"

if [ -n "$BACKUP_REMOTE" ]; then
  echo "==> Copying to ${BACKUP_REMOTE}"
  if command -v aws >/dev/null 2>&1; then
    aws s3 cp "$OUT" "${BACKUP_REMOTE%/}/$(basename "$OUT")"
  else
    echo "WARN: BACKUP_REMOTE set but aws CLI not found — kept local copy only" >&2
  fi
else
  echo "==> BACKUP_REMOTE unset: local copy only."
  echo "    A backup on the same host does not survive losing the host."
fi

echo "==> Pruning dumps older than ${RETAIN_DAYS} days"
find "$BACKUP_DIR" -name 'reasoner-*.dump' -type f -mtime "+${RETAIN_DAYS}" -print -delete

echo "==> Done. $(find "$BACKUP_DIR" -name 'reasoner-*.dump' -type f | wc -l) dump(s) retained."
