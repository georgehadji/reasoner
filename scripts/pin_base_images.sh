#!/usr/bin/env bash
# security-remediation-plan.md Phase 6 item 4: pin Docker base images by
# digest instead of a mutable tag, so a `latest`/`2-alpine`/etc retag upstream
# can't silently swap what gets built.
#
# Requires registry access (Docker Hub). Resolves the digest each image tag
# currently points to and rewrites every `FROM <image>:<tag>` /
# `image: <image>:<tag>` line to `<image>:<tag>@sha256:<digest>` (tag kept
# alongside the digest for human readability; the digest is what's enforced).
#
# Run locally, review the diff, commit:
#   bash scripts/pin_base_images.sh
set -euo pipefail
cd "$(dirname "$0")/.."

FILES=(
    Dockerfile
    ui-next/Dockerfile
    src/reasoner/infrastructure/execution/sandbox_worker/Dockerfile
    src/reasoner/infrastructure/execution/sandbox_worker/sandbox_image/Dockerfile
    docker-compose.yml
)

IMAGES=(
    python:3.12-slim
    node:22-alpine
    docker:27-cli
    alpine:3.21
    caddy:2-alpine
    postgres:16-alpine
    valkey/valkey:8.1.8
    tecnativa/docker-socket-proxy:0.2.0
)

for image in "${IMAGES[@]}"; do
    digest=$(docker buildx imagetools inspect "$image" --format '{{json .Manifest}}' \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])')
    echo "$image -> $digest"
    pinned="${image}@${digest}"
    for f in "${FILES[@]}"; do
        [ -f "$f" ] || continue
        # Only repin a bare tag reference, never touch an already-pinned one.
        sed -i -E "s#(^|[[:space:]])${image//\//\\/}([[:space:]]|\$)#\1${pinned}\2#g" "$f"
    done
done

echo "Done. Review the diff before committing — a Dependabot docker-ecosystem"
echo "PR will keep these digests current afterward."
