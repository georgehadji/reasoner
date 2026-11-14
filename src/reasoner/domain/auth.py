"""Auth vocabulary shared by the auth adapters and the API: permission scopes and the login failure."""

from __future__ import annotations

from enum import Enum


class Scope(str, Enum):
    """Permission scopes for API access control."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    PRESET_READ = "preset:read"
    PRESET_WRITE = "preset:write"
    HISTORY_READ = "history:read"
    HISTORY_DELETE = "history:delete"
    CACHE_CLEAR = "cache:clear"
    KEY_MANAGE = "key:manage"


class AuthenticationError(Exception):
    """Authentication failed (bad, expired or revoked credential)."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
