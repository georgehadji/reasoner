# Reasoner End-to-End Encryption (E2EE) Architecture

Reasoner v2.1 implements a comprehensive **Zero-Trust** security architecture. This ensures that data is never in plaintext while moving through the network or residing in storage.

## 1. Data In-Transit (Network Encryption)

### 1.1. External Traffic
All client-to-proxy traffic is protected by TLS 1.3/1.2 via the Caddy reverse proxy.
- **Automatic HTTPS:** Certificates are managed via Let's Encrypt.
- **HSTS:** `Strict-Transport-Security` is enforced with a 1-year max-age, including subdomains and preloading.
- **Secure Cookies:** All authentication and session cookies are flagged as `Secure`, `HttpOnly`, and `SameSite=Lax/Strict`.

### 1.2. Internal Network (Zero-Trust)
Traffic between containers within the Docker network is fully encrypted.
- **Internal PKI:** A `cert-generator` init-container generates a Root CA and leaf certificates for every service (`backend`, `frontend`, `postgres`, `redis`) on startup.
- **Service TLS:**
  - **PostgreSQL:** Strictly requires SSL/TLS for all connections.
  - **Redis:** Operates in TLS-only mode on port 6379; plaintext port is disabled.
  - **FastAPI (Backend):** Serves traffic via Gunicorn/Uvicorn with native TLS enabled.
  - **Next.js (Frontend):** Wraps the standalone server in a Node.js HTTPS proxy.
- **Upstream Verification:** Caddy uses HTTPS to communicate with backends, ensuring the internal network is opaque even to local attackers.

## 2. Data At-Rest (Application-Layer Encryption)

Reasoner protects sensitive information at the application layer before it reaches the database. This prevents data exposure if the database storage or backups are compromised.

### 2.1. Cryptographic Standards

Two ciphers are available. `ENCRYPTION_FORMAT` selects which one NEW writes
use; reads always try both, so flipping this setting is safe and needs no
migration.

- **v1 — Fernet (`cryptography` library, default):** AES-128-CBC with PKCS7
  padding, authenticated by HMAC-SHA256 (encrypt-then-MAC). The 32-byte
  Fernet key is split into a 16-byte signing key and a 16-byte encryption
  key. Unprefixed ciphertext (`gAAAAA...`) — every row written before v2
  existed is in this format. Rotation via `MultiFernet`.
- **v2 — AES-256-GCM (`ENCRYPTION_FORMAT=v2`):** single-pass authenticated
  encryption, ~2-3x faster than Fernet, and does not embed a timestamp in
  the ciphertext the way Fernet does. Prefixed `v2:` (or `v2z:` when
  compressed). Its key is HKDF-derived from the same `ENCRYPTION_KEY` — see
  below for why it is not the raw Fernet key bytes.
- **Mode:** Both are authenticated symmetric encryption with random
  IV/nonce per message.

> **Key separation:** the v2 AES-GCM key is `HKDF-SHA256(fernet_key_bytes,
> info=b"reasoner-encryption-v2-aesgcm")`, **not** the raw 32-byte Fernet key.
> Fernet already splits that key into a 16-byte HMAC half and a 16-byte
> AES-128 half; reusing the same raw bytes directly as a second, unrelated
> algorithm's key would mean AES-128-CBC+HMAC and AES-256-GCM operate on
> overlapping key material — key-separation practice treats that as unsafe
> regardless of whether a concrete attack is currently known against this
> specific pairing. HKDF keeps `ENCRYPTION_KEY` as the only secret operators
> provision, back up, and rotate.

### 2.2. Encrypted Data Fields
Encryption is applied transparently in the persistence layer:
- **API Keys:** Key names and permission scopes are encrypted in the SQLite `auth_store`.
- **Pipeline State:** Entire execution snapshots, including problem descriptions, thoughts, and final solutions, are encrypted in the PostgreSQL `snapshots` table.
- **Event Payloads:** All domain event data (PHASE_COMPLETED, etc.) is encrypted in the `events` table.
- **Read Models:** Denormalized CQRS read models are encrypted in the `read_models` table.

### 2.3. Compression

`EncryptionService.encrypt(data, compress=True)` zlib-compresses payloads at or
above 512 bytes before encrypting, marked by a leading `z` on the ciphertext
(e.g. `zgAAAAA...`). `decrypt()`/`decrypt_bytes()` detect and reverse this
automatically — callers never need to know how a given row was written.

Used for **snapshots** and **read models** only (large, repetitive JSON).
**Not** used for event payloads: they are typically smaller, and their blind
index is generated from the raw text independently of how `_e` is stored.

This is compress-then-encrypt, which leaks approximate plaintext length via
ciphertext size. Acceptable here because these are at-rest blobs with no
attacker-influenced content and no per-request length oracle — do not reuse
this flag for anything network-observable.

## 3. Key Management

Security relies on the protection of `ENCRYPTION_KEY` and `BLIND_INDEX_KEY`.
- **Environment Variables:** `ENCRYPTION_KEY` (comma-separated Fernet keys) and `BLIND_INDEX_KEY` (urlsafe-base64, 32 bytes). Both are documented in `.env.example`.
- **Rotation:** **Prepend** the new key to the comma-separated list — `MultiFernet` encrypts with the **first** key and decrypts with any key in the list. Appending the new key (as an earlier version of this document incorrectly advised) leaves the *old* key as the active encryption key.
- **Fail-closed Guard:** The system refuses to start unless `ENVIRONMENT` is one of `dev`, `development`, `local`, `test`, `testing`, or unset. In those environments only, a per-process ephemeral key is generated and a loud warning is logged — data written under an ephemeral key is unreadable after restart and by other workers.
- **Blind index keys are not rotatable in place.** Changing `BLIND_INDEX_KEY` invalidates every stored index; re-run `scripts/migrate_encryption_v2.py` to rebuild.
- **Blind index digests are truncated to 16 bytes** (128 bits) — a search index needs far less collision resistance than a MAC; this halves index storage versus the full 32-byte HMAC-SHA256.
- **Reindexing** (after a tokenizer or digest-length change, without touching `_e`):
  ```bash
  python scripts/migrate_encryption_v2.py --reindex-blind-index
  ```
  This is distinct from `migrate_encryption_v2.py`'s default legacy-format migration: that pass only touches rows *missing* `_e`/`_blind_index`, so it cannot re-run reindexing on rows that are already fully encrypted. `--reindex-blind-index` targets every encrypted row unconditionally.

## 4. Security Verification
- **Network:** Inter-container traffic can be inspected via `tcpdump` inside the Docker network to confirm TLS encapsulation.
- **Database:** Querying the database directly via `psql` or `sqlite3` will show base64-encoded ciphertexts (`gAAAAA...` for v1, `v2:...`/`v2z:...` for v2) for all protected fields.

## 5. Architecture

`core/ports/crypto_port.py` defines `EncryptionPort` (structural, `@runtime_checkable`)
— `EncryptionService` implements it, and infrastructure call sites (`auth_store.py`,
`postgres_store.py`, `migrate_encryption_v2.py`) type-annotate against the port rather
than the concrete class. There is no `set_encryption_port()` injection yet: every
current caller reads the module-level singleton via `get_encryption_service()`
directly, and none need to swap implementations independently. Add DI when a real
second caller needs it (e.g. an `EncryptedStore` decorator wrapping multiple stores)
— see `ENCRYPTION_ROADMAP.md` P4.
