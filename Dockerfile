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
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

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
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os,ssl,urllib.request; scheme='https' if os.environ.get('SSL_CERTFILE') and os.environ.get('SSL_KEYFILE') else 'http'; ctx=(ssl.create_default_context(cafile='/certs/ca.crt') if os.path.exists('/certs/ca.crt') else ssl._create_unverified_context()) if scheme=='https' else None; urllib.request.urlopen(scheme+'://localhost:8000/api/health', context=ctx)" || exit 1

# Use entrypoint to support env-driven worker count and memory-leak prevention
ENTRYPOINT ["./docker-entrypoint.sh"]
