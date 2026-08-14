"""
API Keys Domain — user-owned programmatic credentials.

Pure domain: token generation, hashing, and lifecycle predicates. No HTTP,
no database.

Token format
------------
``rsn_<env>_<secret>`` where ``secret`` is 32 bytes of ``secrets.token_urlsafe``
entropy. Only the SHA-256 hash is ever persisted; the plaintext is returned
once at creation and cannot be recovered.

SHA-256 (rather than a password KDF) is the right choice here because the
token is 256 bits of CSPRNG output — there is no low-entropy secret to protect
against offline brute force, and the hot authentication path must stay cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

#: Namespace that distinguishes Reasoner keys from OAuth JWTs on the wire.
KEY_NAMESPACE = "rsn"

#: Environment segment. "live" for real traffic, "test" for sandboxes.
LIVE_ENV = "live"
TEST_ENV = "test"

#: Bytes of entropy in the secret segment.
SECRET_BYTES = 32

#: Characters of the token shown in listings, after the namespace/env segments.
PREFIX_SAMPLE_CHARS = 8

#: Scopes a user may grant to their own keys. Administrative scopes are
#: deliberately excluded — a user key can never escalate beyond its owner.
ASSIGNABLE_SCOPES: frozenset[str] = frozenset(
    {"read", "write", "preset:read", "history:read", "history:delete"}
)

DEFAULT_SCOPES: frozenset[str] = frozenset({"read", "preset:read", "history:read"})

#: Hard cap on live keys per user, to bound credential sprawl and the blast
#: radius of a compromised account.
MAX_KEYS_PER_USER = 20


class InvalidScopeError(ValueError):
    """Raised when a caller requests a scope they may not assign to a key."""


@dataclass(frozen=True, slots=True)
class ApiKey:
    """A stored API key. Never holds the plaintext secret."""

    id: UUID
    user_id: UUID
    name: str
    key_hash: str
    key_prefix: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or datetime.now(timezone.utc)) >= self.expires_at

    def is_usable(self, now: Optional[datetime] = None) -> bool:
        """A key authenticates only while it is neither revoked nor expired."""
        return not self.is_revoked and not self.is_expired(now)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": sorted(self.scopes),
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "is_active": self.is_usable(),
        }


@dataclass(frozen=True, slots=True)
class GeneratedKey:
    """A freshly minted key. ``plaintext`` is shown to the user exactly once."""

    plaintext: str
    key_hash: str
    key_prefix: str


def generate_key(env: str = LIVE_ENV) -> GeneratedKey:
    """Mint a new API key with its storable hash and display prefix."""
    secret = secrets.token_urlsafe(SECRET_BYTES)
    plaintext = f"{KEY_NAMESPACE}_{env}_{secret}"
    return GeneratedKey(
        plaintext=plaintext,
        key_hash=hash_key(plaintext),
        key_prefix=f"{KEY_NAMESPACE}_{env}_{secret[:PREFIX_SAMPLE_CHARS]}",
    )


def hash_key(plaintext: str) -> str:
    """SHA-256 hex digest of a plaintext key."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def verify_key(plaintext: str, key_hash: str) -> bool:
    """Constant-time comparison of a candidate key against a stored hash."""
    return hmac.compare_digest(hash_key(plaintext), key_hash)


def looks_like_api_key(token: str) -> bool:
    """Cheap shape check used to route a bearer token to the API-key path.

    Deliberately permissive about the secret segment: an ill-formed token must
    still fail *authentication* rather than be silently treated as a JWT.
    """
    if not token or not token.startswith(f"{KEY_NAMESPACE}_"):
        return False
    parts = token.split("_", 2)
    return len(parts) == 3 and parts[1] in (LIVE_ENV, TEST_ENV) and bool(parts[2])


def normalize_scopes(requested: Optional[set[str]]) -> frozenset[str]:
    """Validate requested scopes, falling back to the read-only default set.

    Raises:
        InvalidScopeError: if any requested scope is not user-assignable.
    """
    if not requested:
        return DEFAULT_SCOPES
    invalid = {s for s in requested if s not in ASSIGNABLE_SCOPES}
    if invalid:
        raise InvalidScopeError(
            f"Unassignable scopes: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(ASSIGNABLE_SCOPES))}."
        )
    return frozenset(requested)
