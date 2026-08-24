"""
Auth Port — Abstract interface for authentication providers.

The domain and application layers depend ONLY on this protocol.
Concrete adapters (Supabase, Auth0, local JWT) implement this interface.
"""

from __future__ import annotations

from typing import Protocol

from reasoner.domain.saas import User


class AuthPort(Protocol):
    """Port for user authentication."""

    async def authenticate(self, token: str) -> User:
        """
        Validate a bearer token and return the canonical User entity.

        Raises:
            AuthenticationError: If token is invalid, expired, or malformed.
        """
        ...

    async def refresh_session(self, token: str) -> str:
        """
        Refresh an access token if supported by the provider.

        Returns:
            New access token string.
        """
        ...
