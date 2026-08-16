# Encryption Roadmap

Implementation plan for the remaining encryption work in Reasoner: architectural
placement, coverage gaps, optimizations, and migration strategy.

**Status:** P0 (correctness), P1+P2 (index cleanup, blind-index truncation, compression), and P3 (port + AES-256-GCM, trimmed — see note in P3) are shipped. P4–P6 below are planned.
**Companion docs:** [`ENCRYPTION.md`](ENCRYPTION.md) (current design), [`ARCHITECTURE_MINDMAP.md`](ARCHITECTURE_MINDMAP.md).

---

## 0. Baseline — what already shipped

Six runtime defects fixed and covered by 46 tests in [`tests/test_encryption.py`](tests/test_encryption.py):

| Fix | File |
|-----|------|
| `row_factory` set — reads no longer raise `ValueError` | `infrastructure/persistence/auth_store.py` |
| `get_encryption_service()` accepts explicit keys (unblocks the migration script) | `security/encryption.py` |
| Unicode-aware blind index (NFKD fold + `\w+` + CJK bigrams) | `security/encryption.py` |
| `decrypt_optional()` — legacy plaintext passes, key mismatch raises | `security/encryption.py` |
| `search_events` decrypts `problem` (was leaking ciphertext) | `infrastructure/persistence/postgres_store.py` |
| Fail-closed key guard outside dev/test | `security/encryption.py` |

**Outstanding operational action:** the tokenizer change alters token derivation, so
stored blind indexes no longer match. Run `scripts/migrate_encryption_v2.py` to reindex.

---

## 1. Architectural placement

### 1.1 The problem

`reasoner.security` does not appear in the `layers` list in [`.importlinter`](.importlinter).
It is architecturally unplaced: `infrastructure.persistence.*` imports
`reasoner.security.encryption` directly, and nothing constrains who else may.
Because it is unlayered the contract cannot catch a future `domain → security`
import, which would drag the `cryptography` dependency into the domain.

### 1.2 The fix — Ports & Adapters, matching the existing convention

Follow the pattern already used by `core/ports/telemetry_port.py`: a
`@runtime_checkable` `Protocol` in `core/ports/`, adapters in `infrastructure/`.

```
core/ports/crypto_port.py          # EncryptionPort, CipherSuite, KeyProviderPort  (Protocols, no crypto imports)
domain/crypto.py                   # BlindIndex, EncryptedField, KeyId  (frozen value objects)
infrastructure/security/
├── __init__.py
├── fernet_cipher.py               # FernetCipher      — v1, current/legacy
├── aesgcm_cipher.py               # AesGcmCipher      — v2
├── envelope_cipher.py             # EnvelopeCipher    — v3, per-record DEK
├── compressing_cipher.py          # CompressingCipher — decorator, any inner cipher
├── key_providers.py               # EnvKeyProvider, KmsKeyProvider, VaultKeyProvider
└── encrypted_store.py             # EncryptedStore decorator for repositories
security/encryption.py             # thin backward-compat shim → infrastructure.security
```

`security/encryption.py` stays as a re-export shim so the ~5 existing import sites
keep working — same technique as `reasoner/models.py` and `reasoner/pipeline.py`.

Then add to `.importlinter`:

```ini
layers =
    reasoner.api
    reasoner.application
    reasoner.infrastructure
    ...
    reasoner.core
    reasoner.security      # ← below core, above domain: leaf, depends on nothing internal
    reasoner.domain
```

**Definition of done:** `lint-imports` passes with no new ignore entries. The exception
budget (58 used / 65 max) must not grow.

### 1.3 Paradigms and patterns, with justification

Each pattern below earns its place by having more than one real implementation or by
removing duplication that already exists. Anything speculative is explicitly deferred.

| Pattern | Where | Why it is justified |
|---------|-------|---------------------|
| **Ports & Adapters** | `EncryptionPort` | Already the house style; keeps `cryptography` out of domain/application |
| **Strategy** | `CipherSuite` → Fernet / AES-GCM / Envelope | Three genuine implementations coexisting during migration |
| **Decorator** | `CompressingCipher(inner)` | Composes with any cipher; avoids a 2×3 class explosion |
| **Decorator** | `EncryptedStore(inner_store, cipher)` | Four+ stores need identical encrypt/decrypt logic that is currently copy-pasted |
| **Self-describing ciphertext** | `v2:`/`v3:` prefixes | Enables dual-read and incremental migration without a big-bang cutover |
| **Value objects (frozen)** | `BlindIndex`, `KeyId` | Matches the project's `@dataclass(frozen=True)` convention; makes "is this hashed yet?" unrepresentable-if-wrong |
| **Envelope encryption** | `EnvelopeCipher` | Enables KEK rotation without data re-encryption, and per-user crypto-shredding |

**Explicitly NOT doing** (YAGNI — add only when a second case appears):

- No cipher *factory* — a dict lookup on the version prefix is enough.
- No `KeyProviderPort` implementations beyond `EnvKeyProvider` until a KMS is actually
  provisioned. Ship the Protocol with one adapter; add KMS/Vault in P5 when needed.
- No generic "encrypted column" ORM layer. The project uses raw asyncpg/aiosqlite.
- No per-field key derivation. One DEK per record is sufficient.

### 1.4 Self-describing ciphertext format

The single most important design decision, because it makes every later migration
incremental instead of a coordinated big-bang cutover.

```
(no prefix)     legacy Fernet          → "gAAAAA..."                detected by prefix sniff
v2:<b64>        AES-256-GCM            → nonce(12) || ct || tag(16)
v3:<b64>        Envelope AES-256-GCM   → hdr(key_id, wrapped_dek) || nonce || ct || tag
z2:<b64>        v2, zlib-compressed    → compression flag folded into the version tag
z3:<b64>        v3, zlib-compressed
```

`decrypt()` dispatches on prefix, so **all** formats stay readable simultaneously.
`encrypt()` always writes the currently configured format. Readers never need to know
what a writer chose — that is what makes lazy re-encryption safe.

---

## 2. Phase plan

Phases are ordered by (value ÷ risk). P1–P2 are cheap and independent; P3 onward
depends on the port from P1.

### P1 — Cheap optimizations, no format change ✅ shipped

**Goal:** reclaim storage and write throughput with zero migration risk.

| Task | File | Notes |
|------|------|-------|
| Drop `idx_events_type` | new `migrations/008_encryption_indexes.sql` | GIN `jsonb_path_ops` over `payload`, but payload is now only `{_e, _blind_index}` — it indexes ciphertext. Pure write amplification |
| Verify `idx_events_search` is actually used | same | Confirm with `EXPLAIN ANALYZE` on a `search_events` query before/after |
| Truncate blind index to 16 bytes | `security/encryption.py` | New `BLIND_INDEX_BYTES` setting (default 16). 128 bits is ample for a search index; halves index size |
| Bundle the reindex | `scripts/migrate_encryption_v2.py` | The P0 tokenizer fix **already** forces a reindex — fold truncation into the same pass so operators run one migration, not two |

```sql
-- migrations/008_encryption_indexes.sql
DROP INDEX IF EXISTS idx_events_type;  -- indexed ciphertext; no query benefit
```

**Risk:** low. Index drop is reversible; blind index change is covered by the reindex
that P0 already mandates.

**DoD:** `EXPLAIN ANALYZE` shows no plan regression; index size measurably down;
`test_blind_index_*` updated for the new length.

---

### P2 — Compression before encryption ✅ shipped

**Goal:** cut snapshot and read-model storage.

Fernet/base64 adds ~33% on top of whatever it is given, and snapshots are large,
repetitive JSON — zlib typically wins 5–10× there.

```python
# infrastructure/security/compressing_cipher.py
class CompressingCipher:
    """Decorator: compress → encrypt. Only worth it above a size threshold."""

    def __init__(self, inner: CipherSuite, min_bytes: int = 512, level: int = 6):
        self._inner, self._min_bytes, self._level = inner, min_bytes, level

    def encrypt(self, data: bytes) -> str:
        if len(data) < self._min_bytes:
            return self._inner.encrypt(data)          # small payload: not worth it
        return "z" + self._inner.encrypt(zlib.compress(data, self._level))

    def decrypt(self, token: str) -> bytes:
        if token.startswith("z"):
            return zlib.decompress(self._inner.decrypt(token[1:]))
        return self._inner.decrypt(token)
```

Apply to `save_snapshot` and `save_read_model` **only** — not to `save_events`
(small payloads, and the blind index needs the raw text anyway).

**Security note:** compress-then-encrypt leaks plaintext length, which is the CRIME/
BREACH class of attack. That requires an attacker who both *controls part of the
plaintext* and *observes ciphertext length across many requests*. Neither holds for
at-rest blobs. Do not extend this to anything attacker-influenced and length-observable.

**DoD:** roundtrip tests including the below/above-threshold boundary; measured
size reduction on a real snapshot; old uncompressed rows still decrypt.

---

### P3 — Extract the port, adopt AES-256-GCM ✅ shipped (trimmed)

**Goal:** make the documented algorithm true, gain speed, and establish the port.

**Shipped, scope trimmed from the original P3a design below:** `core/ports/crypto_port.py`
defines `EncryptionPort` and `CipherSuite` as documented Protocols; `auth_store.py`,
`postgres_store.py`, and `migrate_encryption_v2.py` annotate against `EncryptionPort`
instead of the concrete class. `.importlinter` now lists `reasoner.security` as a real
layer (it was previously absent — nothing enforced its position at all). This closes
the actual gap that motivated the port (an unconstrained `reasoner.security` in the
dependency graph) without the DI-injection half.

**Deliberately NOT shipped:** `set_encryption_port()` injection at the three
composition roots (originally planned below). Every current caller reads the
module-level singleton via `get_encryption_service()` directly, and none need to swap
implementations independently — building that plumbing now would be an interface with
no second caller to justify it. Add it when P4's `EncryptedStore` decorator needs to
inject a cipher across multiple stores.

Also found and fixed in the process: `reasoner/security/` had no `__init__.py` — it
worked only via Python's implicit namespace-package fallback, invisible to grimp's
static analysis until the new layer entry surfaced it (`lint-imports` failed with
"module reasoner.security does not exist" before the fix).

**`AesGcmCipher` — shipped as `_aesgcm_encrypt_raw`/`_aesgcm_decrypt_raw` inside
`EncryptionService`,** not yet a standalone class (same reasoning: no second cipher
consumer needs the class boundary while dispatch-by-prefix inside one method is
simpler). AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.

Two further wins beyond speed: Fernet **embeds a timestamp** in every token (leaking
record write time even if the column is dropped), and its 32-byte key is split into
two 16-byte halves — so it is AES-**128**, not 256, which is what made the original
`ENCRYPTION.md` claim false.

Writes switch to `v2:` (or `v2z:` compressed) only when `ENCRYPTION_FORMAT=v2` is set.
Reads always accept both — verified by a cross-format compatibility matrix test.

**Key handling that wasn't in the original sketch, added during implementation:** the
v2 key is HKDF-derived from the same `ENCRYPTION_KEY` (`info=b"reasoner-encryption-v2-aesgcm"`),
*not* the raw Fernet key bytes — reusing raw key material across two unrelated
algorithms (Fernet's AES-128-CBC+HMAC vs. raw AES-256-GCM) is unsafe by
key-separation practice regardless of whether a concrete attack is known. Also:
`InvalidTag` (AES-GCM's native failure) and any `ValueError`/`TypeError` from
malformed/truncated v2 ciphertext are both normalized to `InvalidToken`, matching
Fernet's existing single-exception-type contract that every caller in the codebase
already relies on — the initial implementation let a truncated v2 token raise a bare
`ValueError` instead, which `auth_store.py`'s `decrypt_optional` path (no catch-all,
by design) would not have caught.

**DoD:** cross-format compatibility matrix test (v1 write → v2 read, and vice versa);
benchmark showing the speedup; `lint-imports` clean.

---

### P4 — Close the coverage gaps

**Goal:** encrypt the stores that are currently plaintext. This is the phase with the
most actual security value.

Verified plaintext today:

| Target | File | Sensitivity |
|--------|------|-------------|
| **Neuro L2 disk cache** | `neuro/cache.py`, `neuro/sessions.py` | **Highest** — problems *and* final syntheses as plain JSON on disk |
| **SQLite event store** | `infrastructure/persistence/event_store_connection.py` | High — same payloads Postgres encrypts; `events.payload`, `snapshots`, `aggregates`, `dead_letter_queue.raw_payload` |
| **Feedback store** | `infrastructure/persistence/feedback_store.py` | Medium — embeds problem text |
| **Error store** | `infrastructure/persistence/error_store.py` | Medium — error payloads carry problem text and model output |
| **`--save-state` files** | `main.py` | Medium — full `PipelineState` dumped unencrypted |
| **Frontend IndexedDB** | `ui-next/src/lib/db.ts` | Medium — conversation history in the browser |

Rather than copy the encrypt/decrypt block a fifth time, introduce the decorator:

```python
# infrastructure/security/encrypted_store.py
class EncryptedStore:
    """Wraps a store, encrypting configured fields on write and decrypting on read."""
    def __init__(self, inner, cipher: EncryptionPort, fields: frozenset[str]): ...
```

Then refactor `postgres_store.py` onto it last, once the decorator is proven by the
new call sites.

**BYOK provider keys.** `api_key_service.py` correctly SHA-256-hashes *Reasoner's own*
keys — right choice, since verification only needs comparison. But if a user's
*upstream* key (OpenRouter/Anthropic) is ever stored, hashing is wrong: it must be
recoverable, so it needs encryption with a per-user DEK (P5). Flag this before the
BYOK feature ships, not after.

**Frontend:** IndexedDB is a separate trust domain — the backend key must never reach
the browser. Use WebCrypto with a key derived from the session, and accept that this
protects against local disk inspection, not against a compromised page.

**DoD:** each store has a "plaintext never hits disk" test in the style of
`test_auth_store_persists_ciphertext_not_plaintext`; legacy plaintext rows still read.

---

### P5 — Envelope encryption

**Goal:** KEK rotation without data re-encryption, and per-user crypto-shredding.

`scripts/migrate_encryption_v2.py` calls the current scheme "envelope encryption", but
it is not: there is no per-record DEK, just direct encryption under one master key.
Real envelope encryption:

```
record → DEK (random, per record or per user)
DEK    → wrapped by KEK (held in KMS/Vault, never in app memory)
stored → v3:{key_id, wrapped_dek, nonce, ciphertext}
```

Two properties this buys that nothing else does:

1. **KEK rotation is O(number of DEKs), not O(data).** Rewrap DEKs; never touch the
   ciphertext. Today, rotating means re-encrypting every row.
2. **Crypto-shredding.** Delete one user's wrapped DEK and their data is
   unrecoverable — a far cleaner GDPR Article 17 erasure story than `DELETE`, and it
   covers backups automatically. Wire this into the existing
   `application/services/data_eraser.py`.

Scope: per-**user** DEK (not per-record) — same erasure property, far fewer keys to
manage. Add a `user_dek` table in `migrations/009_envelope_encryption.sql`.

Ship `EnvKeyProvider` first; add `KmsKeyProvider` only when a KMS is provisioned.

**DoD:** KEK rotation test that rewraps DEKs and confirms ciphertext is untouched;
crypto-shred test proving the record is unrecoverable after DEK deletion.

---

### P6 — Key rotation tooling

**Goal:** make rotation a routine operation rather than a one-way key-list growth.

`MultiFernet.rotate()` is never called anywhere today, so the key list only ever grows
and old ciphertext stays under the original key forever.

`scripts/rotate_encryption_key.py`, modeled on the existing batched, argparse-driven
`migrate_encryption_v2.py`:

- Batched, resumable (checkpoint table), `--dry-run` first.
- Re-encrypts under the new first key; reports rows remaining on the old key.
- Refuses to run unless the old key is still present in `ENCRYPTION_KEY` — the
  guard-rail that prevents the single worst operator error.

Add a `/health/encryption` endpoint reporting active key id, format, and count of
records still on an old key, so "is rotation finished?" is answerable without a query.

**DoD:** rotation drill on a seeded DB; interrupt mid-run and confirm clean resume.

---

## 3. Migration and rollout

The same shape for every phase — this is what self-describing ciphertext buys:

```
1. Deploy readers that understand old + new   (no writers changed)  ← safe to roll back
2. Flip ENCRYPTION_FORMAT to start writing new
3. Lazy re-encrypt on natural write
4. Background backfill for cold rows
5. Verify zero old-format rows, then drop old key
```

Steps 1–2 are independently reversible. Only step 5 is one-way, and it is gated on a
count query proving nothing is left behind.

### Feature flags

| Flag | Default | Controls |
|------|---------|----------|
| `ENCRYPTION_FORMAT` | `v1` | Format for new writes (`v1`/`v2`/`v3`) |
| `ENCRYPTION_COMPRESS` | `false` | P2 compression |
| `BLIND_INDEX_BYTES` | `32` → `16` after P1 | Blind index truncation |
| `ENCRYPTION_KEY_PROVIDER` | `env` | `env`/`kms`/`vault` |

---

## 4. Testing strategy

Extend [`tests/test_encryption.py`](tests/test_encryption.py) (46 tests, all passing):

| Layer | What |
|-------|------|
| **Property-based** | `hypothesis` roundtrip over arbitrary text/bytes — catches the encoding edge cases that fixed fixtures miss |
| **Compatibility matrix** | Every {v1,v2,v3} × {compressed, plain} written and read by every reader version. This is the test that makes rollback safe |
| **Migration** | Idempotency (run twice = same result), interrupt-and-resume, `--dry-run` mutates nothing |
| **Negative** | Tampered ciphertext rejected; wrong key raises rather than silently degrading; truncated token rejected |
| **Plaintext-leak** | Per store: assert the raw DB/file bytes contain no plaintext (pattern already used by `test_auth_store_persists_ciphertext_not_plaintext`) |
| **Performance** | `pytest-benchmark` on encrypt/decrypt per format; guards the P3 speedup claim against regression |

Keep the existing markers (`@pytest.mark.unit` / `integration`) and the 80% coverage gate.

---

## 5. Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Key loss = total data loss** | Critical | Document key backup before P5; KMS with automated backup; `/health/encryption` surfaces key state |
| Blind index reindex missed | High | Already required by P0. Startup warning when index length ≠ `BLIND_INDEX_BYTES` |
| Partial migration leaves mixed formats | Medium | By design — dual-read makes it safe. Backfill reports remaining count |
| Compression length leak | Low | At-rest blobs only; documented in P2; never extend to attacker-influenced data |
| Blind index frequency analysis | Medium | Unsalted per-token HMACs are rankable by frequency by anyone with DB access. Truncation adds collisions (deniability); only index fields actually searched. **Accept and document** — a fully leak-free searchable index needs ORE/SSE, which is out of scope |
| Perf regression from compression | Low | Size threshold; benchmark in CI |

---

## 6. Sequencing

```
P1 (indexes, truncation) ──┐
                           ├─→ independent, ship first
P2 (compression) ──────────┘

P3a (port extraction) ─→ P3b (AES-GCM) ─→ P4 (coverage) ─→ P5 (envelope) ─→ P6 (rotation)
```

P1 and P2 need no port and can ship immediately. P3a is a pure refactor and is the
prerequisite for everything after it. P5 depends on P4 only because the decorator from
P4 is where the per-user DEK lookup naturally hangs.

**Recommended first slice:** P1 + P2. They are low-risk, need no architectural change,
and P1's reindex is already mandatory because of the P0 tokenizer fix — so it costs
one migration run that operators must do regardless.
