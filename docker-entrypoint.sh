#!/bin/sh
# Production entrypoint for Reasoner backend.
# Supports env-driven gunicorn configuration.

set -e

# Run database migrations before starting the server
if [ "${RUN_MIGRATIONS_ON_STARTUP:-true}" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

# Worker count: default 2, overridable via UVICORN_WORKERS env var
WORKERS="${UVICORN_WORKERS:-2}"

# Timeout: default 120s
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

# Max requests before worker restart (prevents memory leaks)
MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-1000}"
MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-50}"

# Keep-alive and graceful timeout. Graceful must exceed PIPELINE_ABSOLUTE_TIMEOUT_SECONDS (600)
# so a deploy lets in-flight runs drain; UvicornWorker heartbeats while draining, so --timeout is safe.
KEEP_ALIVE="${GUNICORN_KEEP_ALIVE:-5}"
GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-660}"

# SSL Configuration (Phase 1: E2EE)
SSL_ARGS=""
if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
    SSL_ARGS="--certfile=$SSL_CERTFILE --keyfile=$SSL_KEYFILE"
fi

exec gunicorn asgi:app \
    -k uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:8000" \
    --workers "$WORKERS" \
    --timeout "$TIMEOUT" \
    --max-requests "$MAX_REQUESTS" \
    --max-requests-jitter "$MAX_REQUESTS_JITTER" \
    --keep-alive "$KEEP_ALIVE" \
    --graceful-timeout "$GRACEFUL_TIMEOUT" \
    --access-logfile - \
    $SSL_ARGS \
    "$@"
