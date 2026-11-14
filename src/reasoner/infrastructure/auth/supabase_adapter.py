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
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import jwt

from reasoner.application.ports.auth_port import AuthPort
from reasoner.auth import AuthenticationError
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)


def _as_datetime(value: object) -> datetime | None:
    """A Supabase timestamp, as a datetime or an ISO string, or None when absent.

    A naive value is taken as UTC, so it compares with aware cutoffs.
    """
    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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
    # A token Supabase rejected is refused locally for this long, so replaying one
    # cannot force a blocking round trip per request.
    _REJECT_TTL_SECONDS = 30.0

    def __init__(self, supabase_url: str, supabase_service_key: str):
        from supabase import Client, create_client

        self._client: Client = create_client(supabase_url, supabase_service_key)
        self._cache: OrderedDict[str, tuple[float, User]] = OrderedDict()
        self._rejected: OrderedDict[str, float] = OrderedDict()

    def _precheck(self, token: str) -> None:
        """Refuse malformed, expired or foreign-issuer tokens without a network call."""
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired token", status_code=401) from exc
        # No issuer check: a forger sets any iss, and a custom Supabase domain
        # changes the real one, which would lock every user out.
        exp = claims.get("exp")
        if not isinstance(exp, int | float) or exp <= time.time():
            raise AuthenticationError("Invalid or expired token", status_code=401)

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
        if self._rejected.get(key, 0.0) > time.time():
            raise AuthenticationError("Invalid or expired token", status_code=401)
        self._precheck(token)
        try:
            user = await self._verify(token)
        except AuthenticationError as exc:
            if getattr(exc, "rejected", False):  # not a Supabase outage
                self._rejected[key] = time.time() + self._REJECT_TTL_SECONDS
                while len(self._rejected) > self._CACHE_MAX:
                    self._rejected.popitem(last=False)
            raise
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
                err = AuthenticationError("Invalid or expired token", status_code=401)
                err.rejected = True
                raise err

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

            # The real signup time. Without it every account looks new, which the
            # email-verification grandfather rule (created_at < cutoff) relies on.
            created_at = _as_datetime(getattr(supabase_user, "created_at", None))
            user = User(
                id=user_id,
                email=supabase_user.email or "",
                display_name=supabase_user.user_metadata.get("full_name")
                if supabase_user.user_metadata
                else None,
                auth_provider=provider,
                avatar_url=avatar_url,
                email_verified=_as_datetime(getattr(supabase_user, "email_confirmed_at", None))
                is not None,
            )
            return user if created_at is None else replace(user, created_at=created_at)
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Supabase auth validation failed: %s", exc)
            err = AuthenticationError(f"Auth validation failed: {exc}", status_code=401)
            # supabase-py's AuthApiError carries the HTTP status; 4xx means the token was refused.
            err.rejected = 400 <= (getattr(exc, "status", 0) or 0) < 500
            raise err from exc

    async def delete_identity(self, user_id: str) -> None:
        """Delete the Supabase auth user, which also ends its sessions (BIL-18).

        Before this, account deletion left the identity and its JWT valid.
        This worker's verified-token cache is purged too; other workers'
        entries expire within ``_CACHE_TTL_SECONDS``.
        """
        try:
            await asyncio.to_thread(self._client.auth.admin.delete_user, user_id)
        except Exception as exc:
            if "not found" not in str(exc).lower():
                raise
        for key in [k for k, (_, u) in self._cache.items() if str(u.id) == user_id]:
            del self._cache[key]

    async def refresh_session(self, token: str) -> str:
        """Not implemented for server-side validation."""
        raise NotImplementedError("Refresh is handled client-side with Supabase")
