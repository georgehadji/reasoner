"""
Local Auth Adapter — Implements AuthPort using local JWT signing.

Used for:
- Development without Supabase connectivity
- Unit tests (deterministic, no network)
- CI pipelines where external auth is undesirable
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

import jwt

from reasoner.domain.saas import User
from reasoner.application.ports.auth_port import AuthPort
from reasoner.auth import AuthenticationError

logger = logging.getLogger(__name__)


class LocalAuthAdapter(AuthPort):
    """
    Development auth adapter using local HS256 JWT.

    Generates and validates tokens with a local secret.
    NEVER use in production.
    """

    def __init__(self, secret: str | None = None):
        from reasoner.core.settings import settings
        raw_secret = secret or settings.JWT_SECRET_KEY
        if not raw_secret or len(raw_secret) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set and at least 32 characters long. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        self._secret = raw_secret
        self._algorithm = "HS256"

    def create_token(
        self,
        user_id: str,
        email: str,
        display_name: str | None = None,
        expires_in_hours: int = 24,
        scopes: list[str] | None = None,
    ) -> str:
        """Create a local JWT for testing."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "email": email,
            "name": display_name,
            "scopes": scopes or [],
            "iat": now,
            "exp": now + timedelta(hours=expires_in_hours),
            "iss": "reasoner-local",
            "aud": "reasoner-api",
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    async def authenticate(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "exp"]},
                audience="reasoner-api",
                issuer="reasoner-local",
            )
            return User(
                id=UUID(payload["sub"]),
                email=payload.get("email", ""),
                display_name=payload.get("name"),
                scopes=set(payload.get("scopes", [])),
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Token has expired", status_code=401) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"Invalid token: {exc}", status_code=401) from exc

    async def refresh_session(self, token: str) -> str:
        raise NotImplementedError("Local adapter does not support refresh")
