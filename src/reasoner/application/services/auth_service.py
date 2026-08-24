"""
Auth Service — Thin wrapper over AuthPort with caching and logging.
"""

from __future__ import annotations

from reasoner.application.ports.auth_port import AuthPort
from reasoner.domain.saas import User


class AuthService:
    def __init__(self, port: AuthPort):
        self._port = port

    async def authenticate(self, token: str) -> User:
        # Future: add Redis cache here (TTL = JWT expiry - 60s)
        return await self._port.authenticate(token)

    async def refresh_session(self, token: str) -> str:
        return await self._port.refresh_session(token)
