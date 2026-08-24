"""Port interface for at-rest encryption — infrastructure/security provides the adapter.

Follows the same shape as ``model_registry_port.py``: the core layer defines the
contract, ``security.encryption.EncryptionService`` implements it. Unlike the
registry port, this one is NOT injected via a setter yet — every current
consumer (``auth_store.py``, ``postgres_store.py``, the migration script) reads
the module-level singleton via ``get_encryption_service()`` directly, and none
of them need to swap implementations independently. Add ``set_encryption_port()``
DI when a real second caller needs it (e.g. the P4 ``EncryptedStore`` decorator
wrapping multiple stores) — introducing it earlier would be an interface with
no second implementation to justify it.

This Protocol exists now because ``reasoner.security`` was absent from
``.importlinter``'s layers, so nothing enforced its position in the dependency
graph. Call sites annotate against ``EncryptionPort`` (not the concrete class)
so the boundary is structurally checked even without runtime injection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EncryptionPort(Protocol):
    """What application/infrastructure code depends on for at-rest encryption.

    Implemented by ``security.encryption.EncryptionService``, which may hold
    more than one cipher (Fernet for legacy reads, AES-256-GCM for new writes
    — see ``ENCRYPTION_FORMAT``); callers never need to know which one wrote
    a given ciphertext.
    """

    def encrypt(self, data: str | bytes, *, compress: bool = False) -> str: ...

    def decrypt(self, token: str | bytes) -> str: ...

    def decrypt_bytes(self, token: str | bytes) -> bytes: ...

    def decrypt_optional(self, value: str | None) -> str | None:
        """Legacy plaintext passes through unchanged; ciphertext that fails
        to decrypt raises rather than being silently treated as plaintext."""
        ...

    def generate_blind_index(self, text: str) -> list[str]: ...


@runtime_checkable
class CipherSuite(Protocol):
    """One encryption algorithm's raw encrypt/decrypt, no framing concerns.

    Compression and format-prefix dispatch live in ``EncryptionPort``, not
    here — a ``CipherSuite`` only ever sees/returns raw bytes. Documented for
    the implementations already living inside ``EncryptionService``
    (``_fernet_encrypt_raw``/``_aesgcm_encrypt_raw`` and their decrypt
    counterparts); not yet extracted to standalone classes since dispatch by
    version prefix inside one class is simpler while there are only two.
    """

    version: str

    def encrypt(self, data: bytes) -> bytes: ...

    def decrypt(self, token: bytes) -> bytes: ...
