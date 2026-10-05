# ── Backend Dockerfile ──
FROM python:3.14-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment for isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ──
FROM python:3.14-slim AS runtime

WORKDIR /app

# Install runtime libpq dependency
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user (Critical Enhancement 5.2)
# The uid/gid are pinned: docker-compose.yml's cert-generator chowns
# /certs/backend.key to 10001 so gunicorn (running as appuser) can read the
# TLS key from the read-only /certs mount. Keep the two in sync.
RUN groupadd -r -g 10001 appuser && useradd -r -u 10001 -g appuser -d /app -s /sbin/nologin appuser

# Copy application code
COPY src/ src/
COPY asgi.py .
COPY main.py .
COPY start_all.py .

# Copy Alembic config + migrations: docker-entrypoint.sh runs
# `alembic upgrade head` under `set -e` on every boot, and alembic.ini's
# script_location (migrations/alembic) has to exist in the image or that
# fails before gunicorn ever starts.
COPY alembic.ini .
COPY migrations/ migrations/

# Create directories for volumes and set ownership
RUN mkdir -p cache history uploads && chown -R appuser:appuser /app

# Copy entrypoint script
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

USER appuser

EXPOSE 8000

# Health check. gunicorn is started with --certfile/--keyfile (TLS) whenever
# SSL_CERTFILE and SSL_KEYFILE are set (see docker-entrypoint.sh), so the
# scheme here has to follow the same env vars or an HTTP probe against a
# TLS-only port fails every check and the container is never "healthy".
# When TLS is on, verify against the internal CA docker-compose.yml mounts
# at /certs/ca.crt; only skip verification if that CA isn't present (e.g. a
# non-compose deployment terminating TLS some other way).
# Python 3.13+ turns on VERIFY_X509_STRICT in create_default_context(), which
# rejects a CA certificate that lacks the keyUsage extension. Volumes created
# before the cert-generator started adding keyUsage still hold such a CA, so
# strict checking is cleared here (hostname and chain checks stay on).
# start-period covers `alembic upgrade head` plus gunicorn booting 8 workers.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import os,ssl,urllib.request; scheme='https' if os.environ.get('SSL_CERTFILE') and os.environ.get('SSL_KEYFILE') else 'http'; ctx=(ssl.create_default_context(cafile='/certs/ca.crt') if os.path.exists('/certs/ca.crt') else ssl._create_unverified_context()) if scheme=='https' else None; ctx and setattr(ctx,'verify_flags',ctx.verify_flags & ~ssl.VERIFY_X509_STRICT); urllib.request.urlopen(scheme+'://localhost:8000/api/health', context=ctx)" || exit 1

# Use entrypoint to support env-driven worker count and memory-leak prevention
ENTRYPOINT ["./docker-entrypoint.sh"]
