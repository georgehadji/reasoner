"""
Encryption Service for Data at Rest (Phase 3: E2EE)

Provides authenticated symmetric encryption for sensitive data storage, plus
keyed blind indexes so encrypted columns remain searchable. Two ciphers:
Fernet (AES-128-CBC + HMAC-SHA256, "v1", default — every row ever written
uses this) and AES-256-GCM ("v2", opt-in via ENCRYPTION_FORMAT). decrypt()
auto-detects which cipher wrote a given token; callers never choose.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import threading
import unicodedata
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

# Environments that may run without operator-supplied keys. Anything else
# (production, prod, staging, ...) must fail closed rather than silently
# generating an ephemeral key that orphans every previously stored record.
_EPHEMERAL_KEY_ENVIRONMENTS = {"", "dev", "development", "local", "test", "testing"}

# Below this size, zlib's header/table overhead can exceed what it saves;
# above it (snapshots, read models) real JSON typically compresses 5-10x.
_COMPRESS_MIN_BYTES = 512

# Blind index digest length in bytes. Full HMAC-SHA256 is 32 bytes; a search
# index needs far less collision resistance than a MAC does. 16 bytes (128
# bits) is still practically uncollidable and halves index storage.
_BLIND_INDEX_BYTES = 16

# Cipher selected for NEW writes; reads always accept every format below
# regardless of this setting, so flipping it needs no migration.
#   v1 (default) - Fernet: AES-128-CBC + HMAC-SHA256. Unprefixed ciphertext,
#                   for compatibility with every row written before v2 existed.
#   v2            - AES-256-GCM, single-pass authenticated encryption.
#                   ~2-3x faster than Fernet and does not embed a timestamp
#                   in the ciphertext the way Fernet does.
_VALID_WRITE_FORMATS = {"v1", "v2"}

_AESGCM_NONCE_BYTES = 12
_AESGCM_HKDF_INFO = b"reasoner-encryption-v2-aesgcm"

# Unicode-aware tokenizer: \w matches letters/digits in every script, so
# Cyrillic, Greek, Arabic and CJK text produce tokens instead of nothing.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Scripts written without spaces between words. Whole-run tokens are useless
# for search there, so these also emit character bigrams.
_UNSPACED_SCRIPT_RE = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]"
)


def _looks_like_ciphertext(value: str) -> bool:
    """
    True if `value` has the shape of a token this module could have written,
    under any format (Fernet v1, plain or compressed; AES-GCM v2, plain or
    compressed).

    Used to tell "this is legacy plaintext, pass it through" apart from
    "this is ciphertext we failed to decrypt", which is a key problem and
    must not be silently swallowed. Fernet's version byte (0x80) always
    base64-encodes to a leading "gAAAAA", and "v2:"/"v2z:" are literal tags
    this module alone emits — this is a structural check, not a guess; real
    plaintext colliding with it is not a practical risk.
    """
    if not isinstance(value, str):
        return False
    return value.startswith(("gAAAAA", "zgAAAAA", "v2:", "v2z:"))


def _derive_aesgcm_key(fernet_key_material: bytes) -> bytes:
    """
    Derive an AES-256-GCM key independent of the raw Fernet key material
    that seeds it.

    Fernet already splits its 32-byte key into a 16-byte HMAC-signing half
    and a 16-byte AES-128 half. Reusing those same raw bytes directly as a
    second, unrelated algorithm's key would mean AES-128-CBC+HMAC and
    AES-256-GCM operate on overlapping/derived key material — cryptographic
    key-separation practice treats that as unsafe regardless of whether a
    concrete attack is currently known against this specific pairing. HKDF
    with a fixed `info` label gives v2 its own domain-separated key from the
    one secret operators already manage, so ENCRYPTION_KEY stays the only
    thing that needs provisioning, backing up, and rotating.
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_AESGCM_HKDF_INFO,
    ).derive(fernet_key_material)


def _normalize_tokens(text: str) -> list[str]:
    """
    Normalize free text into deduplicated, script-agnostic search tokens.

    NFKD + combining-mark removal folds accents ("café" -> "cafe") so that
    queries match regardless of how the text was typed.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()

    tokens: list[str] = []
    for token in _TOKEN_RE.findall(folded):
        tokens.append(token)
        if len(token) > 1 and _UNSPACED_SCRIPT_RE.search(token):
            tokens.extend(token[i : i + 2] for i in range(len(token) - 1))

    # dict.fromkeys dedupes while preserving order.
    return list(dict.fromkeys(tokens))


class EncryptionService:
    """
    Handles symmetric encryption and decryption for sensitive data at rest.

    Supports key rotation via MultiFernet (v1) and per-key AES-GCM ciphers
    (v2) — same key list drives both. Also provides functionality for
    generating blind indexes.
    """

    def __init__(
        self,
        keys: str | list[str] | None = None,
        blind_index_key: str | None = None,
        write_format: str | None = None,
    ):
        """
        Initialize with one or more encryption keys and an optional blind index key.
        The first key in the list is used for encryption.
        All keys are used for decryption.

        write_format selects the cipher for NEW writes ("v1" Fernet, default;
        "v2" AES-256-GCM). Falls back to ENCRYPTION_FORMAT, then "v1". Every
        key in `keys` is usable for decryption under both formats regardless
        of this setting.
        """
        environment = os.environ.get("ENVIRONMENT", "").strip().lower()
        allow_ephemeral = environment in _EPHEMERAL_KEY_ENVIRONMENTS

        if keys is None:
            # Fallback to environment variable for encryption keys
            keys_env = os.environ.get("ENCRYPTION_KEY")
            if not keys_env:
                if not allow_ephemeral:
                    raise RuntimeError(
                        f"ENCRYPTION_KEY environment variable is missing in ENVIRONMENT={environment!r}!"
                    )

                logger.warning(
                    "ENCRYPTION_KEY not found. Generating a per-process ephemeral key. "
                    "Data written now will be UNREADABLE after restart and by other "
                    "workers. Set ENCRYPTION_KEY for any persistent or multi-worker run."
                )
                keys = [Fernet.generate_key().decode()]
            else:
                keys = [k.strip() for k in keys_env.split(",") if k.strip()]

        if isinstance(keys, str):
            keys = [keys]

        if not keys:
            raise ValueError("No encryption keys provided.")

        try:
            self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
        except Exception as e:
            logger.error(f"Failed to initialize EncryptionService: {e}")
            raise ValueError(f"Invalid encryption key(s) provided: {e}") from e

        # AES-256-GCM (v2). One derived cipher per configured key, same
        # order as `keys`, so v2 rotation follows the same "try each key on
        # read" rule as v1. `Fernet(k.encode())` above already validated
        # every key decodes to exactly 32 bytes, so this decode cannot fail.
        self._aesgcm_ciphers = [
            AESGCM(_derive_aesgcm_key(base64.urlsafe_b64decode(k.encode())))
            for k in keys
        ]

        if write_format is None:
            write_format = os.environ.get("ENCRYPTION_FORMAT", "v1").strip().lower()
        if write_format not in _VALID_WRITE_FORMATS:
            raise ValueError(
                f"ENCRYPTION_FORMAT must be one of {sorted(_VALID_WRITE_FORMATS)}, got {write_format!r}"
            )
        self._write_format = write_format

        # Blind Index Key
        if not blind_index_key:
            blind_index_key = os.environ.get("BLIND_INDEX_KEY")
            if not blind_index_key:
                if not allow_ephemeral:
                    raise RuntimeError(
                        f"BLIND_INDEX_KEY environment variable is missing in ENVIRONMENT={environment!r}!"
                    )
                logger.warning(
                    "BLIND_INDEX_KEY not found. Generating a per-process ephemeral key. "
                    "Blind indexes written now will not match after restart."
                )
                blind_index_key = Fernet.generate_key().decode()

        try:
            self._blind_index_key = base64.urlsafe_b64decode(blind_index_key.encode())
        except Exception as e:
            raise ValueError(f"BLIND_INDEX_KEY is not valid urlsafe base64: {e}") from e

    def _aesgcm_encrypt_raw(self, data: bytes) -> bytes:
        """AES-256-GCM encrypt under the first configured key. nonce || ciphertext(+tag)."""
        nonce = os.urandom(_AESGCM_NONCE_BYTES)
        return nonce + self._aesgcm_ciphers[0].encrypt(nonce, data, None)

    def _aesgcm_decrypt_raw(self, encoded: bytes) -> bytes:
        """
        Base64-decode and AES-256-GCM decrypt, trying every configured key
        (rotation support).

        Fernet promises exactly one exception (InvalidToken) for any
        malformed input, including bad base64 or a truncated token — every
        existing caller across the codebase relies on that single-exception
        contract. AESGCM/base64 make no such promise on their own (a short
        or corrupt token can raise ValueError, not InvalidTag), so every
        failure mode here — bad encoding, wrong length, wrong key — is
        normalized to InvalidToken rather than leaking library-specific
        exception types to callers that only catch InvalidToken.
        """
        last_exc: Exception | None = None
        try:
            token = base64.urlsafe_b64decode(encoded)
            nonce, ct = token[:_AESGCM_NONCE_BYTES], token[_AESGCM_NONCE_BYTES:]
            for cipher in self._aesgcm_ciphers:
                try:
                    return cipher.decrypt(nonce, ct, None)
                except InvalidTag as exc:
                    last_exc = exc
        except (ValueError, TypeError) as exc:
            last_exc = exc
        raise InvalidToken("AES-GCM decryption failed: no configured key matches.") from last_exc

    def encrypt(self, data: str | bytes, *, compress: bool = False) -> str:
        """
        Encrypt data and return a URL-safe base64 encoded string.

        Uses whichever cipher `write_format` selects ("v1" Fernet by default,
        "v2" AES-256-GCM). compress=True zlib-compresses payloads at or above
        _COMPRESS_MIN_BYTES before encrypting (snapshots/read models are
        large, repetitive JSON). Below the threshold it is skipped, since
        deflate's own overhead can exceed what a small payload saves.
        Callers with small or already-compact payloads (events; the blind
        index is generated from the raw text independently either way)
        should leave this False.
        """
        if isinstance(data, str):
            data = data.encode()

        do_compress = compress and len(data) >= _COMPRESS_MIN_BYTES
        payload = zlib.compress(data) if do_compress else data

        if self._write_format == "v2":
            token = base64.urlsafe_b64encode(self._aesgcm_encrypt_raw(payload)).decode()
            return f"v2z:{token}" if do_compress else f"v2:{token}"

        token = self._fernet.encrypt(payload).decode()
        return f"z{token}" if do_compress else token

    def _decrypt_raw(self, token: str | bytes) -> bytes:
        """Decrypt under whichever cipher wrote this token, reversing compress=True."""
        if isinstance(token, bytes):
            token = token.decode()

        if token.startswith("v2z:"):
            return zlib.decompress(self._aesgcm_decrypt_raw(token[4:].encode()))
        if token.startswith("v2:"):
            return self._aesgcm_decrypt_raw(token[3:].encode())

        # v1 Fernet. The "z" marker is only ever produced by our own
        # encrypt(); a genuine Fernet token always follows immediately after
        # it, so this is a structural check, not a plaintext-content guess.
        compressed = token.startswith("z") and token[1:].startswith("gAAAAA")
        inner = (token[1:] if compressed else token).encode()

        raw = self._fernet.decrypt(inner)
        return zlib.decompress(raw) if compressed else raw

    def decrypt(self, token: str | bytes) -> str:
        """
        Decrypt a token and return the plaintext string.
        """
        try:
            return self._decrypt_raw(token).decode()
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or key mismatch.")
            raise
        except Exception as e:
            logger.error(f"Unexpected decryption error: {e}")
            raise

    def decrypt_bytes(self, token: str | bytes) -> bytes:
        """
        Decrypt a token and return the plaintext bytes.
        """
        try:
            return self._decrypt_raw(token)
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or key mismatch.")
            raise

    def generate_blind_index(self, text: str) -> list[str]:
        """
        Generate a list of deterministic, blinded hashes for search terms.
        These hashes can be stored and searched without compromising data privacy.

        Tokenization is Unicode-aware, so non-Latin text is indexable; scripts
        written without spaces additionally emit character bigrams. Digests
        are truncated to _BLIND_INDEX_BYTES — a search index needs far less
        collision resistance than a MAC.
        """
        blind_indexes = []
        for token in _normalize_tokens(text):
            # Use HMAC-SHA256 for deterministic hashing with a secret key
            h = hmac.new(self._blind_index_key, token.encode(), hashlib.sha256)
            digest = h.digest()[:_BLIND_INDEX_BYTES]
            blind_indexes.append(base64.urlsafe_b64encode(digest).decode())
        return blind_indexes

    def decrypt_optional(self, value: str | None) -> str | None:
        """
        Decrypt a value that may predate encryption being enabled.

        Legacy plaintext is returned unchanged, but a value that is
        ciphertext-shaped (either cipher, either format) and fails to
        decrypt raises: that means a key mismatch, which must never be
        silently downgraded to "looks like plaintext".
        """
        if value is None or value == "":
            return value
        if not _looks_like_ciphertext(value):
            return value
        return self.decrypt(value)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet-compatible encryption key."""
        return Fernet.generate_key().decode()


# Global singleton instance
_instance: EncryptionService | None = None
_lock = threading.Lock()


def get_encryption_service(
    encryption_key: str | list[str] | None = None,
    blind_index_key: str | None = None,
) -> EncryptionService:
    """
    Get or create the global EncryptionService instance (thread-safe).

    Passing explicit keys returns a dedicated instance instead of the
    singleton, so callers such as the migration script can operate on a
    specific key set without mutating global state.
    """
    if encryption_key is not None or blind_index_key is not None:
        return EncryptionService(keys=encryption_key, blind_index_key=blind_index_key)

    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EncryptionService()
    return _instance


def reset_encryption_service() -> None:
    """Drop the cached singleton. Intended for tests and key-rotation drills."""
    global _instance
    with _lock:
        _instance = None
