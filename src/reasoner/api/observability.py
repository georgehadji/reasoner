"""Production observability gate.

Production must not run blind.  The original gate demanded
LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY and raised at import time — but
docker-compose.yml hardcodes ENVIRONMENT=production while neither
.env.example nor DEPLOY.md ever mentioned those keys, so the documented
`docker compose up -d --build` crash-looped the backend on a fresh clone.

The gate now accepts any one configured backend instead of a single vendor.
"""

from __future__ import annotations


def active_observability_backends() -> list[str]:
    """Return the observability backends that are actually usable right now.

    Prometheus counts when the client library is importable (the metrics
    endpoint has real output rather than an empty body); Sentry and Langfuse
    count when their credentials are configured.
    """
    from reasoner.core.settings import settings
    from reasoner.infrastructure.metrics import _PROMETHEUS_AVAILABLE

    backends: list[str] = []
    if _PROMETHEUS_AVAILABLE:
        backends.append("prometheus (/api/metrics)")
    if settings.SENTRY_DSN:
        backends.append("sentry")
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        backends.append("langfuse")
    return backends


def require_observability_backend() -> list[str]:
    """Raise unless at least one observability backend is available.

    prometheus-client is a hard dependency in requirements.txt, so this only
    fires on a stripped install that dropped it.
    """
    backends = active_observability_backends()
    if not backends:
        raise RuntimeError(
            "CRITICAL: no observability backend is configured and "
            "ENVIRONMENT=production. Enable at least one: install "
            "prometheus-client (in requirements.txt, exposes /api/metrics), "
            "set SENTRY_DSN, or set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY."
        )
    return backends
