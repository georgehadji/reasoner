"""Production must boot without Langfuse credentials.

docker-compose.yml hardcodes ENVIRONMENT=production, so a gate that demanded
LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY crash-looped the backend on a fresh
clone — those keys appeared in no .env.example and no DEPLOY.md.
"""

from __future__ import annotations

import pytest

from reasoner.api.observability import (
    active_observability_backends,
    require_observability_backend,
)
from reasoner.core.settings import settings


def test_prometheus_alone_satisfies_the_gate(monkeypatch):
    """A default install ships prometheus-client and nothing else configured."""
    monkeypatch.setattr(settings, "SENTRY_DSN", None)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", None)

    backends = require_observability_backend()

    assert any("prometheus" in b for b in backends)


def test_partial_langfuse_credentials_do_not_count(monkeypatch):
    """One of the two keys leaves the Langfuse client disabled, so it is not a backend."""
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-only-half")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", None)

    assert "langfuse" not in active_observability_backends()


def test_configured_backends_are_all_reported(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://key@sentry.example/1")
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-x")

    backends = active_observability_backends()

    assert "sentry" in backends
    assert "langfuse" in backends


def test_gate_raises_when_nothing_is_available(monkeypatch):
    """Only reachable on a stripped install that dropped prometheus-client."""
    monkeypatch.setattr(
        "reasoner.infrastructure.metrics._PROMETHEUS_AVAILABLE", False, raising=False
    )
    monkeypatch.setattr(settings, "SENTRY_DSN", None)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", None)

    with pytest.raises(RuntimeError, match="no observability backend"):
        require_observability_backend()


def test_prometheus_client_is_installed():
    """A silent fallback makes /api/metrics return an empty body, so pin it here."""
    from reasoner.infrastructure.metrics import _PROMETHEUS_AVAILABLE

    assert _PROMETHEUS_AVAILABLE, "prometheus-client must be installed (requirements.txt)"


def test_sentry_sdk_is_installed():
    """init_sentry() silently no-ops without the SDK, losing all error reporting."""
    from reasoner.api.sentry import _HAS_SENTRY

    assert _HAS_SENTRY, "sentry-sdk must be installed (requirements.txt)"
