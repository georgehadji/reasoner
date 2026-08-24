"""
Regression tests for reasoner.security.encryption and its persistence consumers.

Each test here corresponds to a defect that was verified broken at runtime:
  - AuthStore reads raised ValueError (no aiosqlite row_factory)
  - get_encryption_service() rejected the kwargs its only caller passes
  - Blind indexes were empty for every non-ASCII language
  - A key mismatch silently produced an API key with zero scopes
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet, InvalidToken

from reasoner.security.encryption import (
    EncryptionService,
    get_encryption_service,
    reset_encryption_service,
)


@pytest.fixture
def keys() -> tuple[str, str, str]:
    """Two Fernet keys plus a blind-index key."""
    return (
        Fernet.generate_key().decode(),
        Fernet.generate_key().decode(),
        base64.urlsafe_b64encode(os.urandom(32)).decode(),
    )


@pytest.fixture
def svc(keys) -> EncryptionService:
    k1, _, bi = keys
    return EncryptionService(keys=[k1], blind_index_key=bi)


# ── core roundtrip ──


@pytest.mark.unit
@pytest.mark.parametrize(
    "plaintext",
    ["hello", "", "Проблема оптимизации", "如何优化系统", "café résumé"],
)
def test_roundtrip_preserves_plaintext(svc, plaintext):
    assert svc.decrypt(svc.encrypt(plaintext)) == plaintext


@pytest.mark.unit
def test_roundtrip_handles_large_payloads(svc):
    """Snapshots and event payloads can be large; built inline so the
    parametrize id does not blow past the 32767-char env var limit."""
    large = "x" * 1_000_000
    assert svc.decrypt(svc.encrypt(large)) == large


@pytest.mark.unit
def test_bytes_roundtrip_preserves_binary(svc):
    payload = bytes(range(256))
    assert svc.decrypt_bytes(svc.encrypt(payload)) == payload


@pytest.mark.unit
def test_ciphertext_is_nondeterministic(svc):
    """A fresh IV per message: identical plaintext must not yield identical ciphertext."""
    assert svc.encrypt("same") != svc.encrypt("same")


@pytest.mark.unit
def test_tampered_ciphertext_is_rejected(svc):
    token = svc.encrypt("authentic")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidToken):
        svc.decrypt(tampered)


# ── compression (P2) ──


@pytest.mark.unit
def test_compress_true_below_threshold_is_not_compressed(svc):
    """Below _COMPRESS_MIN_BYTES, compression is skipped: no 'z' marker."""
    token = svc.encrypt("short", compress=True)
    assert not token.startswith("z")
    assert svc.decrypt(token) == "short"


@pytest.mark.unit
def test_compress_true_above_threshold_is_compressed_and_marked(svc):
    large = "the quick brown fox jumps over the lazy dog. " * 50
    token = svc.encrypt(large, compress=True)
    assert token.startswith("zgAAAAA")
    assert svc.decrypt(token) == large


@pytest.mark.unit
def test_compress_false_never_adds_marker_regardless_of_size(svc):
    large = "x" * 10_000
    token = svc.encrypt(large, compress=False)
    assert not token.startswith("z")
    assert svc.decrypt(token) == large


@pytest.mark.unit
def test_decrypt_transparently_handles_both_compressed_and_plain(svc):
    """A single decrypt() call must not need to know how a token was written."""
    large = "y" * 5_000
    plain_token = svc.encrypt(large, compress=False)
    compressed_token = svc.encrypt(large, compress=True)
    assert plain_token != compressed_token
    assert svc.decrypt(plain_token) == svc.decrypt(compressed_token) == large


@pytest.mark.unit
def test_compressed_bytes_roundtrip(svc):
    payload = bytes(range(256)) * 50
    token = svc.encrypt(payload, compress=True)
    assert token.startswith("z")
    assert svc.decrypt_bytes(token) == payload


@pytest.mark.unit
def test_tampered_compressed_ciphertext_is_rejected(svc):
    token = svc.encrypt("x" * 5_000, compress=True)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidToken):
        svc.decrypt(tampered)


@pytest.mark.unit
def test_wrong_key_on_compressed_token_raises_invalid_token(keys):
    k1, k2, bi = keys
    token = EncryptionService(keys=[k2], blind_index_key=bi).encrypt("z" * 5_000, compress=True)
    with pytest.raises(InvalidToken):
        EncryptionService(keys=[k1], blind_index_key=bi).decrypt(token)


@pytest.mark.unit
def test_decrypt_optional_recognizes_compressed_tokens_as_ciphertext(svc):
    """
    A compressed token must never be mistaken for legacy plaintext just
    because it starts with 'z' instead of 'g' — decrypt_optional has to see
    through the marker, not stop at the first character.
    """
    large = "real ciphertext, not a key named zebra " * 20
    token = svc.encrypt(large, compress=True)
    assert svc.decrypt_optional(token) == large


@pytest.mark.unit
def test_decrypt_optional_still_treats_bare_z_text_as_legacy_plaintext(svc):
    """A literal legacy value that merely starts with 'z' is not ciphertext-shaped."""
    assert svc.decrypt_optional("zebra-key-name") == "zebra-key-name"


# ── key rotation ──


@pytest.mark.unit
def test_rotation_decrypts_old_ciphertext_and_encrypts_with_first_key(keys):
    k_new, k_old, bi = keys
    old_token = EncryptionService(keys=[k_old], blind_index_key=bi).encrypt("legacy")

    rotated = EncryptionService(keys=[k_new, k_old], blind_index_key=bi)
    assert rotated.decrypt(old_token) == "legacy"

    # New writes must use the FIRST key, so a new-key-only service can read them.
    fresh = rotated.encrypt("current")
    assert EncryptionService(keys=[k_new], blind_index_key=bi).decrypt(fresh) == "current"


@pytest.mark.unit
def test_missing_key_raises_invalid_token(keys):
    k1, k2, bi = keys
    token = EncryptionService(keys=[k2], blind_index_key=bi).encrypt("data")
    with pytest.raises(InvalidToken):
        EncryptionService(keys=[k1], blind_index_key=bi).decrypt(token)


# ── v2: AES-256-GCM ──


@pytest.fixture
def svc_v2(keys) -> EncryptionService:
    k1, _, bi = keys
    return EncryptionService(keys=[k1], blind_index_key=bi, write_format="v2")


@pytest.mark.unit
def test_v2_write_format_produces_v2_prefixed_tokens(svc_v2):
    assert svc_v2.encrypt("hello").startswith("v2:")


@pytest.mark.unit
@pytest.mark.parametrize(
    "plaintext",
    ["hello", "", "Проблема оптимизации", "如何优化系统", "café résumé"],
)
def test_v2_roundtrip_preserves_plaintext(svc_v2, plaintext):
    assert svc_v2.decrypt(svc_v2.encrypt(plaintext)) == plaintext


@pytest.mark.unit
def test_v2_bytes_roundtrip_preserves_binary(svc_v2):
    payload = bytes(range(256))
    assert svc_v2.decrypt_bytes(svc_v2.encrypt(payload)) == payload


@pytest.mark.unit
def test_v2_ciphertext_is_nondeterministic(svc_v2):
    """Fresh nonce per message: identical plaintext must not yield identical ciphertext."""
    assert svc_v2.encrypt("same") != svc_v2.encrypt("same")


@pytest.mark.unit
def test_v2_compression_roundtrips_and_is_marked(svc_v2):
    large = "the quick brown fox jumps over the lazy dog. " * 50
    token = svc_v2.encrypt(large, compress=True)
    assert token.startswith("v2z:")
    assert svc_v2.decrypt(token) == large


@pytest.mark.unit
def test_v2_tampered_ciphertext_is_rejected(svc_v2):
    token = svc_v2.encrypt("authentic")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidToken):
        svc_v2.decrypt(tampered)


@pytest.mark.unit
def test_v2_wrong_key_raises_invalid_token_not_invalid_tag(keys):
    """
    InvalidTag (the cryptography library's native AES-GCM failure) must be
    normalized to InvalidToken — every existing caller across the codebase
    catches InvalidToken specifically, expecting it regardless of which
    cipher wrote the ciphertext it's reading.
    """
    k1, k2, bi = keys
    token = EncryptionService(keys=[k2], blind_index_key=bi, write_format="v2").encrypt("secret")
    with pytest.raises(InvalidToken):
        EncryptionService(keys=[k1], blind_index_key=bi, write_format="v2").decrypt(token)


@pytest.mark.unit
def test_v2_rotation_decrypts_old_ciphertext_and_encrypts_with_first_key(keys):
    k_new, k_old, bi = keys
    old_token = EncryptionService(keys=[k_old], blind_index_key=bi, write_format="v2").encrypt("legacy")

    rotated = EncryptionService(keys=[k_new, k_old], blind_index_key=bi, write_format="v2")
    assert rotated.decrypt(old_token) == "legacy"

    fresh = rotated.encrypt("current")
    assert EncryptionService(keys=[k_new], blind_index_key=bi, write_format="v2").decrypt(fresh) == "current"


@pytest.mark.unit
def test_v2_decrypt_optional_recognizes_v2_tokens_as_ciphertext(svc_v2):
    assert svc_v2.decrypt_optional(svc_v2.encrypt("real data")) == "real data"


@pytest.mark.unit
@pytest.mark.parametrize(
    "malformed",
    [
        "v2:",                    # empty payload after prefix
        "v2:not-valid-base64!!!", # invalid base64 characters
        "v2:QQ==",                 # valid base64, but far too short to be nonce+tag
        "v2z:QQ==",
    ],
)
def test_v2_malformed_token_raises_invalid_token_not_value_error(svc_v2, malformed):
    """
    Regression: base64-decoding a v2 token happened outside the exception
    handler that normalizes failures, so a truncated/corrupt row raised a
    bare ValueError instead of InvalidToken. auth_store.py's decrypt_optional
    path has no catch-all fallback (by design, see the key-mismatch test
    above) — an unnormalized ValueError there would crash the auth request
    instead of surfacing as a clean, expected failure mode.
    """
    with pytest.raises(InvalidToken):
        svc_v2.decrypt(malformed)


@pytest.mark.unit
def test_v2_malformed_token_via_decrypt_optional_raises_invalid_token(svc_v2):
    with pytest.raises(InvalidToken):
        svc_v2.decrypt_optional("v2:not-valid-base64!!!")


@pytest.mark.unit
def test_invalid_write_format_raises_actionable_error(keys):
    k1, _, bi = keys
    with pytest.raises(ValueError, match="ENCRYPTION_FORMAT"):
        EncryptionService(keys=[k1], blind_index_key=bi, write_format="v99")


@pytest.mark.unit
def test_write_format_falls_back_to_env(monkeypatch, keys):
    k1, _, bi = keys
    monkeypatch.setenv("ENCRYPTION_FORMAT", "v2")
    svc = EncryptionService(keys=[k1], blind_index_key=bi)
    assert svc.encrypt("x").startswith("v2:")


# ── cross-format: the property that makes phased rollout safe ──


@pytest.mark.unit
def test_v1_writer_and_v2_writer_share_keys_and_cross_read(keys):
    """
    The whole point of format switching: a v1-writing service and a
    v2-writing service configured with the SAME key must each be able to
    read what the other wrote. This is what makes flipping ENCRYPTION_FORMAT
    a safe, reversible, zero-migration operation.
    """
    k1, _, bi = keys
    v1 = EncryptionService(keys=[k1], blind_index_key=bi, write_format="v1")
    v2 = EncryptionService(keys=[k1], blind_index_key=bi, write_format="v2")

    v1_token = v1.encrypt("from v1")
    v2_token = v2.encrypt("from v2")

    assert v2.decrypt(v1_token) == "from v1"
    assert v1.decrypt(v2_token) == "from v2"


@pytest.mark.unit
def test_cross_format_matrix_with_compression(keys):
    k1, _, bi = keys
    v1 = EncryptionService(keys=[k1], blind_index_key=bi, write_format="v1")
    v2 = EncryptionService(keys=[k1], blind_index_key=bi, write_format="v2")
    large = "shared plaintext content " * 100

    tokens = {
        "v1_plain": v1.encrypt(large, compress=False),
        "v1_compressed": v1.encrypt(large, compress=True),
        "v2_plain": v2.encrypt(large, compress=False),
        "v2_compressed": v2.encrypt(large, compress=True),
    }
    for label, token in tokens.items():
        assert v1.decrypt(token) == large, label
        assert v2.decrypt(token) == large, label


@pytest.mark.unit
def test_aesgcm_key_is_not_the_raw_fernet_key_material(keys):
    """
    Guards the HKDF key-separation decision: the derived AES-GCM key must
    not equal the raw Fernet key bytes it was derived from, and must not
    equal the two 16-byte halves Fernet itself splits that key into.
    """
    import base64 as b64

    from reasoner.security.encryption import _derive_aesgcm_key

    k1, _, _ = keys
    raw = b64.urlsafe_b64decode(k1.encode())
    derived = _derive_aesgcm_key(raw)

    assert len(derived) == 32
    assert derived != raw
    assert derived != raw[:16]
    assert derived != raw[16:]


@pytest.mark.unit
def test_aesgcm_key_derivation_is_deterministic(keys):
    from reasoner.security.encryption import _derive_aesgcm_key

    k1, _, _ = keys
    raw = base64.urlsafe_b64decode(k1.encode())
    assert _derive_aesgcm_key(raw) == _derive_aesgcm_key(raw)


# ── EncryptionPort conformance ──


@pytest.mark.unit
def test_encryption_service_satisfies_encryption_port(svc):
    from reasoner.core.ports.crypto_port import EncryptionPort

    assert isinstance(svc, EncryptionPort)


# ── blind index ──


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "optimization problem",   # latin
        "Проблема оптимизации",   # cyrillic
        "最適化の問題",             # japanese
        "如何优化系统",             # chinese
        "مشكلة التحسين",           # arabic
        "βελτιστοποίηση",         # greek
        "최적화 문제",              # korean
    ],
)
def test_blind_index_is_non_empty_for_every_script(svc, text):
    """Regression: the old ASCII-only regex produced [] for all non-Latin input."""
    assert svc.generate_blind_index(text), f"empty blind index for {text!r}"


@pytest.mark.unit
def test_blind_index_is_deterministic_across_instances(keys):
    k1, _, bi = keys
    a = EncryptionService(keys=[k1], blind_index_key=bi)
    b = EncryptionService(keys=[k1], blind_index_key=bi)
    assert a.generate_blind_index("shared term") == b.generate_blind_index("shared term")


@pytest.mark.unit
def test_blind_index_differs_under_different_keys(keys):
    k1, _, bi = keys
    other_bi = base64.urlsafe_b64encode(os.urandom(32)).decode()
    a = EncryptionService(keys=[k1], blind_index_key=bi)
    b = EncryptionService(keys=[k1], blind_index_key=other_bi)
    assert a.generate_blind_index("secret") != b.generate_blind_index("secret")


@pytest.mark.unit
def test_blind_index_folds_case_and_accents(svc):
    assert svc.generate_blind_index("Café") == svc.generate_blind_index("cafe")


@pytest.mark.unit
def test_blind_index_emits_bigrams_for_unspaced_scripts(svc):
    """CJK has no word spaces, so a substring query must still match."""
    doc = svc.generate_blind_index("如何优化系统")
    query = svc.generate_blind_index("优化")
    assert query and set(query).issubset(set(doc))


@pytest.mark.unit
def test_blind_index_deduplicates_repeats(svc):
    idx = svc.generate_blind_index("repeat repeat repeat")
    assert len(idx) == len(set(idx)) == 1


@pytest.mark.unit
def test_blind_index_reveals_no_plaintext(svc):
    assert all("secret" not in tok for tok in svc.generate_blind_index("secret"))


@pytest.mark.unit
def test_blind_index_digest_is_truncated_to_16_bytes(svc):
    """
    Regression: originally stored the full 32-byte HMAC-SHA256 (44-char b64)
    per token. A search index needs far less collision resistance than a
    MAC; 16 bytes halves storage.
    """
    token = svc.generate_blind_index("word")[0]
    decoded = base64.urlsafe_b64decode(token.encode())
    assert len(decoded) == 16


# ── decrypt_optional: legacy plaintext vs. real key mismatch ──


@pytest.mark.unit
def test_decrypt_optional_passes_legacy_plaintext_through(svc):
    assert svc.decrypt_optional("not encrypted yet") == "not encrypted yet"


@pytest.mark.unit
@pytest.mark.parametrize("empty", [None, ""])
def test_decrypt_optional_handles_empty(svc, empty):
    assert svc.decrypt_optional(empty) == empty


@pytest.mark.unit
def test_decrypt_optional_raises_on_key_mismatch(keys):
    """
    The critical distinction: ciphertext we cannot decrypt is an operator error,
    never something to silently treat as plaintext.
    """
    k1, k2, bi = keys
    token = EncryptionService(keys=[k2], blind_index_key=bi).encrypt("sensitive")
    with pytest.raises(InvalidToken):
        EncryptionService(keys=[k1], blind_index_key=bi).decrypt_optional(token)


# ── key configuration guards ──


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["production", "prod", "staging", "PRODUCTION"])
def test_refuses_ephemeral_key_outside_dev(monkeypatch, environment):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        EncryptionService()


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["dev", "development", "local", "test", ""])
def test_allows_ephemeral_key_in_dev(monkeypatch, environment):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("BLIND_INDEX_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", environment)
    svc = EncryptionService()
    assert svc.decrypt(svc.encrypt("dev data")) == "dev data"


@pytest.mark.unit
def test_malformed_blind_index_key_raises_actionable_error(keys):
    k1, _, _ = keys
    with pytest.raises(ValueError, match="base64"):
        EncryptionService(keys=[k1], blind_index_key="!!!not-base64!!!")


@pytest.mark.unit
def test_malformed_encryption_key_raises_actionable_error():
    with pytest.raises(ValueError, match="Invalid encryption key"):
        EncryptionService(keys=["not-a-fernet-key"])


# ── get_encryption_service ──


@pytest.mark.unit
def test_get_encryption_service_returns_singleton(monkeypatch, keys):
    k1, _, bi = keys
    monkeypatch.setenv("ENCRYPTION_KEY", k1)
    monkeypatch.setenv("BLIND_INDEX_KEY", bi)
    reset_encryption_service()
    try:
        assert get_encryption_service() is get_encryption_service()
    finally:
        reset_encryption_service()


@pytest.mark.unit
def test_get_encryption_service_accepts_explicit_keys(keys):
    """
    Regression: scripts/migrate_encryption_v2.py calls this with both kwargs.
    The old zero-arg signature made the migration script raise TypeError.
    """
    k1, _, bi = keys
    svc = get_encryption_service(encryption_key=k1, blind_index_key=bi)
    assert svc.decrypt(svc.encrypt("migrated")) == "migrated"


@pytest.mark.unit
def test_explicit_keys_do_not_poison_the_singleton(monkeypatch, keys):
    k1, k2, bi = keys
    monkeypatch.setenv("ENCRYPTION_KEY", k1)
    monkeypatch.setenv("BLIND_INDEX_KEY", bi)
    reset_encryption_service()
    try:
        shared = get_encryption_service()
        one_off = get_encryption_service(encryption_key=k2, blind_index_key=bi)
        assert one_off is not shared
        assert get_encryption_service() is shared
    finally:
        reset_encryption_service()


# ── AuthStore integration ──


@pytest.fixture
def auth_store(tmp_path, monkeypatch, keys):
    k1, _, bi = keys
    monkeypatch.setenv("ENCRYPTION_KEY", k1)
    monkeypatch.setenv("BLIND_INDEX_KEY", bi)
    reset_encryption_service()
    from reasoner.infrastructure.persistence.auth_store import AuthStore

    yield AuthStore(tmp_path / "auth.db")
    reset_encryption_service()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_store_roundtrips_encrypted_metadata(auth_store):
    """Regression: reads raised ValueError because row_factory was never set."""
    await auth_store.insert(
        key_hash="hash-1",
        name="ci-deploy-key",
        scopes={"read", "write"},
        is_active=True,
        rate_limit_tier="high",
        created_at=datetime.now(UTC),
        expires_at=None,
        created_by="admin",
    )

    row = await auth_store.get_by_hash("hash-1")
    assert row is not None
    assert row["name"] == "ci-deploy-key"
    assert row["scopes"] == {"read", "write"}
    assert row["is_active"] is True

    assert len(await auth_store.list_all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_store_persists_ciphertext_not_plaintext(auth_store):
    """The whole point: plaintext must never touch the database file."""
    import aiosqlite

    await auth_store.insert(
        key_hash="hash-2",
        name="super-secret-name",
        scopes={"admin"},
        is_active=True,
        rate_limit_tier="default",
        created_at=datetime.now(UTC),
        expires_at=None,
        created_by=None,
    )

    async with aiosqlite.connect(auth_store._db_path) as conn:
        async with conn.execute("SELECT name, scopes FROM api_keys") as cur:
            name, scopes = await cur.fetchone()

    assert "super-secret-name" not in name
    assert "admin" not in scopes
    assert name.startswith("gAAAAA") and scopes.startswith("gAAAAA")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_store_raises_rather_than_dropping_scopes_on_key_mismatch(
    auth_store, keys
):
    """
    Regression: the old broad `except Exception` fallback returned an API key
    with an EMPTY scope set when the key had rotated away — a silent
    authorization change instead of a loud failure.
    """
    _, k2, bi = keys
    await auth_store.insert(
        key_hash="hash-3",
        name="rotated",
        scopes={"admin", "write"},
        is_active=True,
        rate_limit_tier="default",
        created_at=datetime.now(UTC),
        expires_at=None,
        created_by=None,
    )

    auth_store._encryption = EncryptionService(keys=[k2], blind_index_key=bi)
    with pytest.raises(InvalidToken):
        await auth_store.get_by_hash("hash-3")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_store_reads_legacy_plaintext_rows(auth_store):
    """Rows written before encryption was enabled must still be readable."""
    import aiosqlite

    async with aiosqlite.connect(auth_store._db_path) as conn:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY, name TEXT NOT NULL, scopes TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                rate_limit_tier TEXT NOT NULL DEFAULT 'default',
                created_at TEXT NOT NULL, expires_at TEXT, created_by TEXT,
                last_used_at TEXT, usage_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await conn.execute(
            "INSERT INTO api_keys (key_hash, name, scopes, is_active, rate_limit_tier,"
            " created_at, usage_count) VALUES (?, ?, ?, 1, 'default', ?, 0)",
            ("legacy-1", "old-plaintext-key", json.dumps(["read"]),
             datetime.now(UTC).isoformat()),
        )
        await conn.commit()

    row = await auth_store.get_by_hash("legacy-1")
    assert row["name"] == "old-plaintext-key"
    assert row["scopes"] == {"read"}
