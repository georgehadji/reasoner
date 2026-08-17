"""Entrypoint: ``python -m reasoner.infrastructure.execution.sandbox_worker``.

Binds to all interfaces *inside this container's own network namespace* —
docker-compose.yml never publishes this port to the host, so it's reachable
only from other containers on the internal Compose network (i.e. `backend`).
"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("SANDBOX_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("SANDBOX_WORKER_PORT", "8901"))
    uvicorn.run(
        "reasoner.infrastructure.execution.sandbox_worker.app:app",
        host=host,
        port=port,
        log_level="info",
    )
