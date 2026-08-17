# Sandbox-worker service image — the ONLY container that talks to Docker
# (via docker-socket-proxy, never the raw socket; see docker-compose.yml).
# Distinct from sandbox_image/Dockerfile, which builds the per-job container
# that this worker launches for each execution request.
#
# Build context is the repo root (docker-compose.yml build.context: .) so
# this can COPY the reasoner package.

FROM docker:27-cli AS docker-cli

FROM python:3.12-slim
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0,<0.117.0" \
    "uvicorn[standard]>=0.27.0,<0.35.0" \
    "httpx>=0.27.0,<0.29.0" \
    "pydantic>=2.0"

COPY src/reasoner /app/reasoner
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1

# Runs as its own non-root account — separate from both the per-job sandbox
# UID (65532, sandbox_image/Dockerfile) and the API container's account.
RUN groupadd -g 10001 sandboxworker \
    && useradd -u 10001 -g sandboxworker -M -s /usr/sbin/nologin sandboxworker
USER sandboxworker

EXPOSE 8901
CMD ["python", "-m", "reasoner.infrastructure.execution.sandbox_worker"]
