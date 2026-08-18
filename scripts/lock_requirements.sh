#!/usr/bin/env bash
# security-remediation-plan.md Phase 6 item 4: hash-locked Python deps.
#
# Regenerates requirements.lock.txt (hash-pinned, `pip install --require-hashes`
# safe) from requirements.txt via pip-tools. Requires PyPI network access.
#
# Run locally after touching requirements.txt, then commit the result:
#   bash scripts/lock_requirements.sh
#
# CI (.github/workflows/security.yml `lockfile-freshness`) reruns this and
# fails the build if the committed lockfile is stale — that's the enforcement
# mechanism, not this script.
set -euo pipefail
cd "$(dirname "$0")/.."

pip-compile \
    --generate-hashes \
    --allow-unsafe \
    --output-file=requirements.lock.txt \
    requirements.txt
