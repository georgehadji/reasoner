"""Production must never serve the local HS256 auth adapter (get_auth_adapter).

Regression: the adapter was stored in the module global before the production
guard ran, and the early return at the top skipped the guard on later calls. The
first request raised; every request after it was authenticated by LocalAuthAdapter.
"""

import pytest

import reasoner.infrastructure.auth as auth
from reasoner.core.settings import settings
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter


@pytest.fixture
def production_without_supabase(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setattr(auth, "_auth_adapter", None)
    yield
    auth._auth_adapter = None  # leave no adapter behind for later tests


def test_every_call_refuses_local_adapter_in_production(production_without_supabase):
    for _ in range(3):
        with pytest.raises(RuntimeError, match="not allowed in production"):
            auth.get_auth_adapter()
    assert auth._auth_adapter is None


def test_local_adapter_still_served_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "testing")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setattr(auth, "_auth_adapter", None)
    try:
        assert isinstance(auth.get_auth_adapter(), LocalAuthAdapter)
        assert isinstance(auth.get_auth_adapter(), LocalAuthAdapter)
    finally:
        auth._auth_adapter = None
