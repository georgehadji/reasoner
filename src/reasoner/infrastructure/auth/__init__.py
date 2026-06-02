"""
Auth adapter factory.

Selects the appropriate auth adapter based on environment settings.
"""

from __future__ import annotations

import threading
from typing import Optional

from reasoner.core.settings import settings
from reasoner.application.ports.auth_port import AuthPort

_auth_adapter: Optional[AuthPort] = None
_auth_lock = threading.Lock()


def get_auth_adapter() -> AuthPort:
    """Get or create the global auth adapter."""
    global _auth_adapter
    if _auth_adapter is not None:
        return _auth_adapter

    with _auth_lock:
        # Double-checked locking
        if _auth_adapter is not None:
            return _auth_adapter

        env = settings.ENVIRONMENT
        supabase_url = settings.SUPABASE_URL
        supabase_service_key = settings.SUPABASE_SERVICE_ROLE_KEY

        if env == "production" and supabase_url and supabase_service_key:
            from .supabase_adapter import SupabaseAuthAdapter
            _auth_adapter = SupabaseAuthAdapter(supabase_url, supabase_service_key)
        elif env == "testing":
            from .local_adapter import LocalAuthAdapter
            _auth_adapter = LocalAuthAdapter()
        else:
            # Development fallback: try Supabase, fall back to local
            if supabase_url and supabase_service_key:
                try:
                    from .supabase_adapter import SupabaseAuthAdapter
                    _auth_adapter = SupabaseAuthAdapter(supabase_url, supabase_service_key)
                except Exception:
                    from .local_adapter import LocalAuthAdapter
                    _auth_adapter = LocalAuthAdapter()
            else:
                from .local_adapter import LocalAuthAdapter
                _auth_adapter = LocalAuthAdapter()

    # Security guard: prevent local HS256 auth in production
    if settings.ENVIRONMENT == "production":
        from .local_adapter import LocalAuthAdapter
        if isinstance(_auth_adapter, LocalAuthAdapter):
            raise RuntimeError(
                "LocalAuthAdapter (HS256) is not allowed in production. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for production auth."
            )

    return _auth_adapter


def set_auth_adapter(adapter: AuthPort) -> None:
    """Override the auth adapter (useful for tests)."""
    global _auth_adapter
    with _auth_lock:
        _auth_adapter = adapter
