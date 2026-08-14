# ── Backend Dockerfile ──
FROM python:3.12-slim AS builder

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
FROM python:3.12-slim AS runtime

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

# Alembic config and revisions. docker-entrypoint.sh runs `alembic upgrade head`
# under `set -e`, so omitting these made the container exit 1 on first boot with
# "No config file 'alembic.ini' found" — the schema was never created.
COPY alembic.ini .
COPY migrations/ migrations/

# Create directories for volumes and set ownership
RUN mkdir -p cache history uploads && chown -R appuser:appuser /app

# Copy entrypoint script
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

USER appuser

EXPOSE 8000

# Health check.
# docker-entrypoint.sh gives gunicorn --certfile/--keyfile whenever SSL_CERTFILE
# and SSL_KEYFILE are set, which docker-compose.yml always does — so port 8000
# speaks TLS in the shipped configuration. A hardcoded http:// probe could never
# succeed there, leaving the container permanently unhealthy and defeating the
# health-gated depends_on. Pick the scheme from the same variable, and skip
# verification because these are the internal self-signed certs.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os,ssl,urllib.request; \
s='https' if os.environ.get('SSL_CERTFILE') and os.environ.get('SSL_KEYFILE') else 'http'; \
c=ssl._create_unverified_context() if s=='https' else None; \
urllib.request.urlopen(f'{s}://localhost:8000/api/health', context=c, timeout=5)" || exit 1

# Use entrypoint to support env-driven worker count and memory-leak prevention
ENTRYPOINT ["./docker-entrypoint.sh"]
