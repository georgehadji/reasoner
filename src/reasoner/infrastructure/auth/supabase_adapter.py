"""
Supabase Auth Adapter — Implements AuthPort using supabase-py.

This is the production auth adapter. It validates JWTs against
Supabase's auth server and returns canonical User entities.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from uuid import UUID

import jwt

from reasoner.application.ports.auth_port import AuthPort
from reasoner.auth import AuthenticationError
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)


class SupabaseAuthAdapter(AuthPort):
    """
    Production auth adapter using Supabase Auth.

    Features:
    - JWT validation via Supabase server-side verification
    - Caching recommendation: wrap in AuthService with Redis TTL
    """

    # A verified token is trusted for this long (never past its own exp).
    # shortcut: a token revoked server-side stays valid here for up to 60s.
    _CACHE_TTL_SECONDS = 60.0
    _CACHE_MAX = 1024

    def __init__(self, supabase_url: str, supabase_service_key: str):
        from supabase import Client, create_client

        self._client: Client = create_client(supabase_url, supabase_service_key)
        self._cache: OrderedDict[str, tuple[float, User]] = OrderedDict()

    async def authenticate(self, token: str) -> User:
        """
        Validate a Supabase JWT access token.

        Args:
            token: Bearer token from Authorization header.

        Returns:
            Canonical User entity.

        Raises:
            AuthenticationError: If token is invalid or expired.
        """
        key = hashlib.sha256(token.encode()).hexdigest()
        cached = self._cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]
        user = await self._verify(token)
        expires = time.time() + self._CACHE_TTL_SECONDS
        try:
            # Already verified by Supabase; decoded only to bound the cache.
            exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
            if exp:
                expires = min(expires, float(exp))
        except jwt.PyJWTError:
            pass  # no readable exp: the TTL alone bounds it
        self._cache[key] = (expires, user)
        while len(self._cache) > self._CACHE_MAX:
            self._cache.popitem(last=False)
        return user

    async def _verify(self, token: str) -> User:
        try:
            # Supabase server-side JWT verification: a blocking HTTPS call in
            # supabase-py, so off the event loop.
            response = await asyncio.to_thread(self._client.auth.get_user, token)
            supabase_user = response.user

            if supabase_user is None:
                raise AuthenticationError("Invalid or expired token", status_code=401)

            # Deterministic UUID from Supabase user id
            user_id = UUID(supabase_user.id) if supabase_user.id else UUID(
                bytes=hashlib.sha256(str(supabase_user.id).encode()).digest()[:16]
            )

            # Extract provider from app_metadata (set by Supabase Auth)
            provider = None
            if supabase_user.app_metadata:
                provider = supabase_user.app_metadata.get("provider")

            # Extract avatar from user_metadata (common OAuth field)
            avatar_url = None
            if supabase_user.user_metadata:
                avatar_url = (
                    supabase_user.user_metadata.get("avatar_url")
                    or supabase_user.user_metadata.get("picture")
                )

            return User(
                id=user_id,
                email=supabase_user.email or "",
                display_name=supabase_user.user_metadata.get("full_name")
                if supabase_user.user_metadata
                else None,
                auth_provider=provider,
                avatar_url=avatar_url,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Supabase auth validation failed: %s", exc)
            raise AuthenticationError(f"Auth validation failed: {exc}", status_code=401) from exc

    async def refresh_session(self, token: str) -> str:
        """Not implemented for server-side validation."""
        raise NotImplementedError("Refresh is handled client-side with Supabase")
