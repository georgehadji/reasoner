-- Migration 008: Drop dead index on encrypted event payloads
--
-- idx_events_type was a GIN(jsonb_path_ops) index over events.payload,
-- written back when payload held plaintext JSON. Since Phase 3 (E2EE),
-- payload only ever contains {"_e": <ciphertext>, "_blind_index": [...]} —
-- the index has been indexing opaque ciphertext bytes ever since, which
-- jsonb_path_ops cannot use for any query. It costs write amplification on
-- every event insert for zero query benefit. Full-text search over event
-- content goes through idx_events_search (the blind index) instead, which
-- this migration leaves untouched.

DROP INDEX IF EXISTS idx_events_type;
