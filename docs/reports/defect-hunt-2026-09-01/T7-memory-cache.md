# T7 — Memory, Cache & Self-Healing

Autonomous Defect-Hunt Protocol V7 (proactive). Worktree
`.worktrees/defect-hunt`, branch `chore/defect-hunt-t6`. Budget 8 candidates,
8 spent. Nothing committed, nothing pushed.

Scope: `src/reasoner/neuro/**`, `src/reasoner/healing/**`, and the caching /
fail-safe behaviour of `src/reasoner/hypergate/**`.

---

## PHASE 1 — Defect-surface map

| R | Region (file:function) | Defect classes | Entry reachability | Blast radius | Invariant density |
|---|---|---|---|---|---|
| R1 | `neuro/config.py:_safe_agent_id`, `get_agent_data_dir` | 1 (tenant path) | REACHABLE from asgi:app via `POST /api/neuro/{recall,learn,audit}` → `NeuroService.*` → `TenantManager.get`; also from `main.py`/`headless` via `orchestrator._recall_neuro_context` | EXTERNALLY-VISIBLE | high (traversal, single-segment, collapse) |
| R2 | `neuro/server.py:tenant_key`, `TenantManager.get/_evict_*` | 1, 2, 3 | REACHABLE, same path | EXTERNALLY-VISIBLE | high |
| R3 | `neuro/cache.py:L1Cache.add/search/_load` | 2, 3, 5 | REACHABLE via `NeuroService.ingest` / `recall_chunks` | MODULE (memory content) | medium |
| R4 | `neuro/cache.py:L2Index.add/_save`, `l3_scan` | 2, 3, 5 | REACHABLE, same | MODULE | medium |
| R5 | `neuro/compression.py:_compress_minimal/_compress_aggressive/smart_compress` | 4, 5, 6 | REACHABLE three ways: `/api/neuro/recall?compression=`, `application/pipeline.py:470` (E3 flag), `infrastructure/llm/executor.py:886` (code-fence compression on coding roles) | SYSTEM (content silently altered before it enters a prompt) | low — almost no guards |
| R6 | `neuro/server.py:_cached_compress` | 2 | REACHABLE via `/api/neuro/recall` | LOCAL | medium |
| R7 | `neuro/sessions.py:ingest_async/_start_session/archive_*` | 2, 3, 4 | REACHABLE via `/api/neuro/learn` | MODULE | medium |
| R8 | `hypergate/base_sub_agent.py:execute/_cache_key` | 2 | GUARDED — `HyperGateAgent` is constructed per call (`orchestrator.py:279`, `gate_service.py:269`) and `_cache` is per-instance (`__new__`), so the cache is always cold in the running app | LOCAL today, EXTERNALLY-VISIBLE if the agent is ever hoisted | medium |
| R9 | `hypergate/hyperagent.py:_synthesize/_run_tiebreaker/decide` | 4 (fail-safe) | REACHABLE from every entry point | EXTERNALLY-VISIBLE (routing) | high |
| R10 | `healing/**` | 4 | DEAD from every entry point — nothing under `src/reasoner/` imports `reasoner.healing` except `healing/run_healing.py` itself; both engines are `__main__` dev tools | none at runtime | n/a |

Hunt queue (likelihood x blast_radius x reachability):
R5 > R1/R2 > R3/R4 > R9 > R7 > R8 > R6 > R10.

Three tagged assertions about the map itself:

- **A1 [VF]** `healing/` is unreachable from `asgi:app`, `main.py`,
  `reasoner.headless` and `api/mcp`. Evidence: `grep -rn "from reasoner.healing|import healing" src/reasoner/` returns exactly one hit, inside `healing/run_healing.py`.
- **A2 [VF]** Every `agent_id` that reaches the filesystem does so through
  `get_agent_data_dir` → `_safe_agent_id`; there is no second join site.
  Evidence: `grep -rn agent_id src/reasoner/` — the only `Path(...) / agent_id`
  construction is `config.py:365-368`.
- **A3 [VF]** The HyperGate sub-agent LRU is per-instance, not class-level as
  its docstring claims: `BaseSubAgent.__new__` assigns `instance._cache = {}`.
  Combined with per-request construction of `HyperGateAgent`, the cache never
  survives a request. This makes R8 GUARDED rather than REACHABLE.

---

## PHASE 2 — Suspicion generation

**D1 — HyperGate sub-agent cache key omits `SubAgentInput.context`.**
Under a second `execute()` with the same `problem` but different Phase-1
signals, `base_sub_agent.py:138` returns the cached `SubAgentOutput` computed
from the *first* context, because the key is
`sha256(f"{AGENT_NAME}:{problem}")` while `_llm_call` appends
`json.dumps(inp.context)` to the user prompt.
Class 1 (cache-key completeness) · violates **property (b)** · reachability
GUARDED · severity LOW-as-shipped / HIGH-if-hoisted (silently wrong routing) ·
prior: high — the census names this exact shape as already having occurred here
(the LLM cache that ignored the system prompt) · innocence path: the instance
is rebuilt per request.

**D2 — `_compress_minimal` opens block-comment mode on any line *containing*
`/*`.** Under any input whose line contains `/*` without a later `*/`,
`compression.py:75` sets `in_block = True` and every remaining line is
`continue`d, so `compress()` returns `""`.
Class 6 (compression data integrity) / class 4 (silent truncation) · violates
the module's own stated contract, `MINIMAL = "Removes comments and
whitespace"` · REACHABLE from `/api/neuro/recall`, `pipeline.py:470` and
`executor.py:886` · severity HIGH (silently-wrong-answer: the caller is handed
`""` and told nothing) · prior: high — `/*` is a substring of every glob
(`src/*`), of URLs, and of SQL hints · innocence path: callers only pass real
source in a known language.

**D3 — `TenantManager` eviction produces two live in-memory views of one
on-disk tenant.** Under >`MAX_TENANTS` (100) distinct tenant keys, or 30 min
idle, `_evict_lru_locked` / `_evict_stale_locked` drop a tenant whose `l1`,
`l2` and `index_lock` a still-running request holds. The recreated tenant gets
a *different* `index_lock` over the same `index.json`, and `L2Index.add`
rewrites that file wholesale from its own snapshot.
Class 2 (concurrency) / class 3 (lifecycle) · violates the invariant the
`index_lock` comment states explicitly ("concurrent same-tenant learns raced
two such writes ... silently dropping entries") · REACHABLE but narrow ·
severity MEDIUM (silent loss of memory entries) · innocence path: an evicted
tenant is by definition the least recently used, so nothing holds it.

**D4 — tenant directory collapse under `_safe_agent_id` stripping.** Two
distinct `tenant_key` outputs that differ only in characters outside
`[A-Za-z0-9_-]`, or beyond 128 chars, resolve to one directory while remaining
two in-memory tenants.
Class 1 · would violate **property (a)** · severity CRITICAL if reachable.

**D5 — `L1Cache.add` appends a duplicate in-memory entry behind one file.**
`bundle_id` is `sha256(content)[:12]` and names the file; re-adding identical
content appends a second list entry. Eviction then unlinks the file while the
other copy stays "present" in memory.
Class 3 / class 6 · violates "an entry present in L1 is retrievable after
reload" · REACHABLE via `/api/neuro/learn` with a repeated exchange · severity
MEDIUM (silent memory loss + duplicate recall results consuming `top_k`).

**D6 — `SessionManager.ingest_async` check-then-act across an await.**
`_should_start_new_session()` is read, then `_start_session` is awaited via
`asyncio.to_thread`; concurrent first-ingests each start a session, and the
lock acquired for `self._current_session_file` may not be the file
`_write_entry` finally opens.
Class 2 · severity LOW.

**D7 — `healing/test_generation_engine.py` writes generated files from a
report-driven filename.** `generate_tests_for_error_gaps` interpolates
`gap["function_name"]` straight into a path.
Class 4 · DEAD (A1).

**D8 — `hyperagent._synthesize` subscripts LLM-derived candidate dicts.**
`c["method"]`, `c["confidence"]`, `c["rationale"]` at lines 306 and 411 are
direct subscripts inside a method whose caller's docstring promises
`decide()` "never raises".
Class 5 · would violate **property (c)**.

---

## PHASE 3 — Proof-of-defect

All triggers executed offline. No network, no LLM API calls; routers are
scripted fakes, all filesystem work is under `tmp_path`. The real `~/.neuro`
was never touched.

### D1
- **Trigger — FIRED.** `probe2`: one `TieBreakerSubAgent`, two `execute()`
  calls with the same problem and different `context`. Result:
  `llm_calls = 1`, and the second call returned the first's verdict
  (`{'action': 'direct', ... 'rationale': 'A'}`) although the scripted router
  held a different second reply. Now covered by
  `tests/test_memory_cache_defects_t7.py::test_different_phase1_context_is_not_served_from_cache`.
- **Innocence — CODE-INNOCENT at the system level.** `HyperGateAgent` is built
  inside a function at both call sites (`orchestrator.py:279`,
  `gate_service.py:269`) and `_cache` is per-instance, so the running app never
  reaches a warm cache. The class comment at `hyperagent.py:156` says the same
  thing about the cache that used to live there.
- **Verdict — CONFIRMED (unit) / LATENT (system).** The unit violates
  cache-key completeness demonstrably; the consequence is currently unreachable.

### D2
- **Trigger — FIRED.** `smart_compress("Line one about src/*.ts globs\nLine
  two MUST SURVIVE\nLine three MUST SURVIVE", ext="", level="minimal")`
  returned `''`. Same for `"See https://example.com/* for details\nSECOND
  LINE\nTHIRD LINE"`. Not truncation — total loss.
- **Innocence — NO-DEFENSE-FOUND.** There is no guard, and the three call
  sites all pass content that is not guaranteed to be source in a known
  language: `/api/neuro/recall` compresses conversational memory chunks with
  `ext` derived from a source label that is usually empty; `pipeline.py:470`
  passes `ext` not at all; `executor.py:886` maps an untagged fence to `""`.
  `Language.UNKNOWN` selects the C-style `/* */` pair.
- **Verdict — CONFIRMED.**

### D3
- **Trigger — FIRED (mechanism), STATISTICAL not required (deterministic).**
  Two `L2Index` objects over one directory: `a.add("first")`, then construct
  `b` (models evict+recreate), then `a.add("second-from-stale-view")` and
  `b.add("third")`. A third reload shows `['first', 'third']` — the middle
  entry is gone. Separately, `TenantManager` with `MAX_TENANTS = 2`: after
  eviction and re-get of the same key, `t1 is t1b` → False, `index_lock` is a
  different object, `data_dir` is identical.
- **Innocence — PARTIAL.** The claim "an evicted tenant is not in use" holds
  for the TTL path (30 min idle) but not for `_evict_lru_locked`, which fires
  on capacity and can select a tenant whose long-running recall is still in
  flight. I could not construct an end-to-end trigger through
  `NeuroService` without >100 concurrent tenants, so the *composition* stays
  unproven even though both halves are proven.
- **Verdict — INDETERMINATE (mechanism CONFIRMED, end-to-end reachability
  UNKNOWN).**

### D4
- **Trigger — DID-NOT-FIRE.**
- **Innocence — CODE-INNOCENT, and already regression-guarded.**
  `tenant_key` emits `u-{owner}-{agent_id}` or `a-{agent_id}`. `owner` is
  `str(User.id)` and `User.id` is a `UUID` (`domain/saas.py:37`), i.e. a
  fixed-length string drawn entirely from `[0-9a-f-]`, which survives
  `_safe_agent_id` unchanged. Two distinct UUIDs therefore cannot collapse,
  and the literal `u-`/`a-` prefixes are themselves sanitizer-stable, so the
  anonymous branch can never forge an owned key. This was found and fixed by a
  previous audit; `tests/test_neuro_cache_wiring.py:374-429` guards it
  structurally, and `tests/test_neuro_agent_id_isolation.py` guards traversal.
  Residual: two *anonymous* callers whose `agent_id`s differ only in stripped
  characters do collapse — but an anonymous namespace is keyed on a guessable
  conversation id in the first place, so this adds no capability an attacker
  did not already have.
- **Verdict — CLEARED.**

### D5
- **Trigger — FIRED.** With `l1_max_bundles = 3`, adding `"same"` twice then
  `"b"`, `"c"`: in-memory `['same','b','c']`, on disk two files, and after
  `L1Cache._load()` the surviving content is `['b','c']` — `"same"` is gone
  while the live object still reports it. `search()` also returned `"dup"`
  twice for a single stored memory.
- **Innocence — NO-DEFENSE-FOUND.** No dedupe anywhere on the path;
  `ingest()` builds `content = f"User: {prompt}\nAssistant: {response}"`, so a
  repeated identical exchange (a retry, a resubmitted question) produces a
  byte-identical bundle.
- **Verdict — CONFIRMED.**

### D6
- **Trigger — FIRED, consequence benign.** Five concurrent `ingest_async`
  calls produced 4 session files, but all 5 exchanges persisted and
  `entry_number` came back `[1,2,3,4,5]`.
- **Innocence — partially CODE-INNOCENT.** The observable damage is session
  fragmentation, not data loss. The lock/target mismatch
  (`_get_file_lock(self._current_session_file)` then
  `_write_entry(self._current_session_file, ...)` re-reading the attribute)
  is real but only bites across a session rollover, and each write is a single
  append of one line.
- **Verdict — CLEARED (cosmetic; recorded as an observation).**

### D7
- **Trigger — NOT ATTEMPTED (dead code, A1).**
- **Innocence — site unreachable from every entry point.** `function_name`
  additionally originates from an AST walk of local source, so it is a Python
  identifier by construction.
- **Verdict — CLEARED (out of runtime scope).**

### D8
- **Trigger — DID-NOT-FIRE.**
- **Innocence — CODE-INNOCENT.** The only producer of
  `method_output.result["candidates"]` is
  `MethodClassifierSubAgent._parse_result`, which builds every candidate dict
  literally with all four keys and wraps the whole body in
  `try/except Exception` returning `"candidates": []`. `_failed_output` yields
  `result={}`, and `.get("candidates", []) or []` handles that. Property (c)
  holds on this path.
- **Verdict — CLEARED.**

---

## PHASE 4 — Triage inventory

Ranked by severity x reachability x blast_radius.

| Candidate | Trigger | Innocence | Evidence basis | Status |
|---|---|---|---|---|
| D2 compression drops the whole tail on a mid-line `/*` | FIRED (returns `""`) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — fixed** |
| D5 L1 duplicate content lost on reload | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — fixed** |
| D3 tenant eviction splits the L2 write lock | FIRED (mechanism) | PARTIAL | SUSPECTED | **INDETERMINATE — human review** |
| D1 sub-agent cache key omits `context` | FIRED (unit) | CODE-INNOCENT (system) | VERIFIED DEFECT (unit), latent | **CONFIRMED — fixed (hardening)** |
| D6 session start check-then-act | FIRED, benign | PARTIAL | UNKNOWN (no damaging consequence found) | CLEARED |
| D4 tenant directory collapse | DID-NOT-FIRE | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D8 `_synthesize` subscripts LLM output | DID-NOT-FIRE | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D7 healing generated-test path | not attempted | site unreachable | FALSE (innocent) | CLEARED |

---

## PHASE 5 — Fix design

### Fix 1 — D2 (`src/reasoner/neuro/compression.py`, `_compress_minimal`)

```diff
-            # Simple block comment skip
-            if block_start and block_start in trimmed:
+            # Block comment skip. startswith, not `in`: a mid-line "/*" --
+            # a glob ("src/*.ts"), a URL ("https://x/*"), an SQL hint -- used
+            # to open block mode on ordinary prose, and since no later line
+            # ever closed it the ENTIRE remainder of the text was discarded
+            # and compress() returned "". Losing the tail is a far worse
+            # failure than leaving a trailing comment uncompressed.
+            if block_start and trimmed.startswith(block_start):
                 in_block = True
```

Causal justification: the verified mechanism is *substring* detection of the
block-open marker latching `in_block` on a line that is not a comment. The fix
breaks it by requiring the marker to open the line, which is the same rule the
line-comment branch four lines below already uses. No lower-side-effect fix
exists because the only alternatives are (a) a real tokenizer — far beyond a
15-line change and unnecessary for a best-effort token trimmer — or (b)
suppressing comment stripping for `Language.UNKNOWN`, which would silently
change `executor._compress_prompt_code_blocks` for every untagged code fence
and is a separate design decision, not a defect fix.

Risk: scope = one condition in one function. Side effect: a trailing block
comment on a code line (`x = 1; /* c */`) is now retained rather than dropped,
so minimal compression removes marginally less on such lines — strictly a
smaller token saving, never a loss of content. Regression risk: low; the
existing `test_prompt_compression.py` cases use line comments and
language-tagged fences. Reversibility: trivial (one word).

### Fix 2 — D5 (`src/reasoner/neuro/cache.py`, `L1Cache.add`)

```diff
         bundle = {"id": bundle_id, "content": content, "source": source,
                   "embedding": embedding, "created_at": time.time()}
+        # bundle_id is a digest of the content, and one id maps to one file --
+        # so re-adding identical content must replace, not append. Appending
+        # put two entries in self.bundles behind a single file: search()
+        # returned the same memory twice (burning top_k slots), and evicting
+        # either copy unlinked the file while the other stayed "present" in
+        # memory, so the entry vanished on the next _load().
+        self.bundles = [b for b in self.bundles if b.get("id") != bundle_id]
         self.bundles.append(bundle)
```

Causal justification: the verified mechanism is a one-to-many relation between
a content-addressed file and the in-memory list. The fix breaks it by
restoring one-to-one before the append, so eviction can never unlink a file a
surviving entry depends on. No lower-side-effect fix exists: guarding only the
eviction site (checking whether another entry shares the id) leaves the
duplicate-search-results half of the defect alive, and would be a larger diff.

Risk: scope = one statement in one method. Side effect: re-adding identical
content refreshes `created_at` and `source` instead of creating a second
entry — which is the intended semantics of a content-addressed cache and makes
the TTL behave as documented. Regression risk: low. Reversibility: trivial.
Performance: `O(n)` over at most `l1_max_bundles` (default 50) per add.

### Fix 3 — D1 (`src/reasoner/hypergate/base_sub_agent.py`, `_cache_key`)

```diff
-    def _cache_key(self, problem: str) -> str:
-        return hashlib.sha256(f"{self.AGENT_NAME}:{problem}".encode()).hexdigest()
+    def _cache_key(self, inp: SubAgentInput) -> str:
+        # inp.context is part of the user prompt (see _llm_call), so it must be
+        # part of the key. [comment continues in source]
+        ctx = json.dumps(inp.context, sort_keys=True, default=str) if inp.context else ""
+        return hashlib.sha256(
+            json.dumps([self.AGENT_NAME, inp.problem, ctx]).encode()
+        ).hexdigest()
```

(and the one call site, `cache_key = self._cache_key(inp)`.)

Causal justification: the verified mechanism is a key that does not cover every
input the prompt is built from. The fix breaks it by covering `context` too,
with `sort_keys=True` so dict ordering does not fragment the key and
`default=str` so a non-JSON value degrades instead of raising inside the
helper. Using `json.dumps` of a list rather than an f-string with a separator
avoids both a NUL byte in source and a separator-collision. No lower-side-effect
fix exists; the alternative is deleting the cache, which is a larger and
riskier change for a mechanism that is merely currently inert.

**Cache-invalidation cost (tier-specific rule):** this fix changes a cache key,
so every previously cached entry becomes unreachable. Here the cost is exactly
zero: the cache is per-instance, the instance is per-request, so no entry ever
outlives the request that created it. There are no stale entries — neither
orphaned nor harmful — because there is no persistent store behind this cache.

Fix interactions: none. The three touch disjoint modules, and none of them
share state. Fix 1 and Fix 2 are both on the memory-write/read path but at
different tiers (compression is applied to already-retrieved chunks; the L1
change is at insert).

### Not applied — D3

`[REQUIRES HUMAN REVIEW: cross-boundary mechanism]`. Correcting this requires
either refcounting live tenant references across `TenantManager.get`,
`recall_chunks`, `ingest`, `audit` and `list_sessions`, or making `L2Index.add`
re-read `index.json` under the lock before writing. Both cross a boundary and
touch more than one function, so it is out of the protocol's fix budget. The
larger diff, written out as required:

```diff
--- a/src/reasoner/neuro/cache.py
+++ b/src/reasoner/neuro/cache.py
@@ class L2Index
     async def add(self, content: str, source: str, embedding: list[float],
                   metadata: dict = None) -> str:
         entry_id = hashlib.sha256(content.encode()).hexdigest()[:12]
+        # Re-read before write: a tenant evicted from TenantManager while a
+        # request still holds it leaves two L2Index objects over one
+        # index.json, each rewriting the file from its own stale snapshot.
+        # index_lock cannot serialise them -- eviction hands the recreated
+        # tenant a different lock object.
+        await asyncio.to_thread(self._load)
         self.entries.append({...})
```

plus, in `neuro/server.py`, hoisting `index_lock` out of the per-tenant dict
into a `dict[str, asyncio.Lock]` keyed by resolved `data_dir` that eviction
does not clear. Neither half is sufficient alone: the lock must survive
eviction *and* the writer must not trust a snapshot taken before it.

---

## PHASE 6 — Self-review (RAR)

### Fix 1 (compression)
- Boundary — **FIX HOLDS [VF]**: `""`, `"/*"`, `"/* open\ncode"`, a
  single-line `/* c */`, and a multi-line block all behave correctly
  (`test_boundary_empty_and_marker_only_input`,
  `test_no_regression_real_block_comments_are_still_removed`).
- Invalid input — **FIX HOLDS [VF]**: `smart_compress` still raises
  `ValueError` on an out-of-enum level, which
  `tests/test_neuro_cache_wiring.py:697` relies on; `Literal` validation
  upstream keeps that unreachable from HTTP. Adversarial text with unbalanced
  `*/` or `/*` no longer destroys content.
- State — **FIX HOLDS [VF]**: the function is pure; `in_block` is local.
- Regression — **FIX HOLDS [VF]**: real block comments, Python line comments,
  aggressive signature-only output and `level="none"` verbatim passthrough all
  still behave as documented (four dedicated tests, plus the pre-existing
  `test_prompt_compression.py` suite passing unchanged).
- Concurrency — **FIX HOLDS [VF]**: no shared state.
- New defect — **FIX HOLDS [HYP]**: a trailing block comment on a code line is
  now retained. That is a compression-ratio change, not a correctness change,
  and it is asserted in `test_no_regression_real_block_comments_are_still_removed`
  that standalone block comments are still removed.

### Fix 2 (L1 dedupe)
- Boundary — **FIX HOLDS [VF]**: empty cache, cache at `l1_max_bundles`, and
  re-add of the single existing entry
  (`test_boundary_readd_refreshes_rather_than_grows`).
- Invalid input — **FIX HOLDS [VF]**: `b.get("id")` tolerates a legacy bundle
  loaded from disk with no `id` key (`_load` accepts whatever JSON is there).
- State — **FIX HOLDS [VF]**: a half-written or corrupt bundle file is already
  swallowed by `_load`'s `except Exception`; the filter does not depend on
  well-formedness.
- Regression — **FIX HOLDS [VF]**: distinct content still evicts oldest-first
  and survives a reload (`test_no_regression_distinct_content_still_evicts_oldest_first`).
- Concurrency — **FIX HOLDS [HYP]**: `add` is called only under
  `tenant["index_lock"]` (`server.py:ingest`), and the list rebuild is
  synchronous with no await inside it, so no interleaving is possible within
  one tenant object. The residual risk is exactly D3 (two tenant objects), which
  the fix neither creates nor worsens. Downgraded to [HYP] rather than tested
  because a test would only re-demonstrate D3.
- New defect — **FIX HOLDS [VF]**: the rebuilt list preserves relative order of
  the survivors, which the `created_at` sort in the eviction branch does not
  depend on anyway.

### Fix 3 (cache key)
- Boundary — **FIX HOLDS [VF]**: empty context equals absent context; key is
  order-insensitive over dict keys but value-sensitive
  (`test_boundary_key_is_order_insensitive_but_value_sensitive`).
- Invalid input — **FIX HOLDS [VF]**: a non-JSON-serialisable context value
  does not raise, thanks to `default=str`
  (`test_boundary_empty_context_and_unserialisable_context_still_key`).
- State — **FIX HOLDS [VF]**: `_cache` is still a plain dict populated only on
  a clean, sufficiently confident result.
- Regression — **FIX HOLDS [VF]**: an identical input still hits the cache and
  still issues exactly one LLM call
  (`test_no_regression_identical_input_still_hits_the_cache`); the full
  `tests/test_hypergate.py` suite passes unchanged.
- Concurrency — **FIX HOLDS [HYP]**: the dict is touched only from the single
  event loop that runs `asyncio.gather` over the five sub-agents, and each
  sub-agent owns its own dict, so there are no two concurrent writers to one
  cache. Verified by construction (per-instance `_cache`, per-agent
  `AGENT_NAME`), not by a repeated-trial harness.
- New defect — **FIX HOLDS [VF]**: `json` was already imported in the module;
  no new import, no new dependency, no ruff delta.

No FIX BREAKS on any vector, so no revision round was needed.

---

## PHASE 7 — Tests

`tests/test_memory_cache_defects_t7.py`, 17 tests, all executed.

- Proof-of-defect, one per verified defect:
  `test_midline_block_marker_does_not_discard_the_rest_of_the_text`,
  `test_re_adding_identical_content_does_not_lose_it_on_reload`,
  `test_different_phase1_context_is_not_served_from_cache`.
- Boundary: 3 parametrised mid-line-marker shapes, empty/marker-only input,
  duplicate-search, re-add-refreshes, key order-insensitivity,
  empty/unserialisable context.
- No-regression: real block comments still removed, Python line comments still
  removed, aggressive still signature-only, `level="none"` verbatim, distinct
  content still evicts oldest-first, identical sub-agent input still caches.

Results.

```
# with the fixes applied
tests/test_memory_cache_defects_t7.py .................  17 passed

# with the three source files reverted to HEAD (fixes removed)
8 failed, 9 passed in 102.77s

# new tests + every neighbouring suite that touches the changed modules
tests/test_memory_cache_defects_t7.py tests/test_neuro_cache_wiring.py
tests/test_prompt_compression.py tests/test_hypergate.py
tests/test_neuro_agent_id_isolation.py
  114 passed, 6 warnings in 85.60s
```

The 8 failures are exactly the three proof-of-defect tests plus their boundary
companions; every no-regression test passes in both states, which is the point
of calling them no-regression tests.

Gates: `python scripts/ruff_ratchet.py --max 2243` → `ruff violations: 2243`,
`PASS`. My ruff delta is **0**; I did **not** edit the ratchet constant in
`scripts/ci-local.sh` or `.github/workflows/test.yml`.

---

## PHASE 8 — Verdict, coverage and residual risk

**Surface audited.** `neuro/compression.py` (all of it), `neuro/cache.py`
(`L1Cache`, `L2Index`, `l3_scan`), `neuro/config.py` (`_safe_agent_id`,
`get_agent_data_dir`, `get_persona`), `neuro/server.py` (`tenant_key`,
`TenantManager`, `_cached_compress`, `NeuroService.{recall_chunks, ingest,
audit, list_sessions, health}`, the router and its `_owner` dependency),
`neuro/sessions.py` (ingest, session lifecycle, archival, search, stats),
`hypergate/base_sub_agent.py`, `hypergate/hyperagent.py`,
`hypergate/models.py`, `hypergate/sub_agents/{method_classifier, tie_breaker}.py`,
`healing/test_generation_engine.py` (reachability only).

**Surface NOT audited.** `neuro/providers.py` (542 lines of provider adapters —
grepped for caches and key material, found none, but its retry/fallback logic
was not analysed), `neuro/cli.py`, the persona/config YAML loader
(`config.py:1-340`), `healing/introspection_engine.py` (797 lines),
`healing/evolution_agent.py`, `healing/telemetry_exporter.py`,
`healing/run_healing.py` — all four skipped on the strength of A1 (dead from
every entry point), not on the strength of reading them. The remaining
HyperGate sub-agents (`language_detector`, `complexity_estimator`,
`direct_detector`, `web_detector`, `image_model_selector`) were read only for
their cache/parse contract, not audited for classification correctness.

**Defect classes covered.** 1 (cross-tenant leakage / cache-key completeness),
2 (concurrency), 3 (resource lifecycle), 4 (error paths), 5 (boundary/type),
6 (compression data integrity) — all six, at varying depth. Class 2 is the
thinnest: I proved mechanisms, not races under load, and ran no repeated-trial
harness because no candidate reduced to a probabilistic interleaving I could
isolate offline.

**Confirmed by severity.**
- HIGH — 1: D2, `src/reasoner/neuro/compression.py:75` (now :80).
- MEDIUM — 1: D5, `src/reasoner/neuro/cache.py:84`.
- LOW (latent) — 1: D1, `src/reasoner/hypergate/base_sub_agent.py:137`.
- CRITICAL — 0. No cross-tenant leakage was found.

**Cleared as innocent — 4:** D4, D6, D7, D8.

**Residual UNKNOWN set.**
- D3's end-to-end reachability (tenant eviction racing an in-flight request).
- Whether `neuro/providers.py` fallback ordering can serve one tenant's
  embedding to another — not examined.
- `healing/introspection_engine.py` behaviour if ever wired to a runtime path.
- Whether any deployment sets `TOKEN_OPTIMIZATION["context_compression"]`, which
  determines how badly D2 was biting `pipeline.py:470` in practice.

**Clean-claim scope.** Regions R1–R9 were audited for defect classes 1–6 and,
apart from the three confirmed above, no VERIFIED defect was found. This is
*not* a claim that memory is isolated or that the cache is correct.

**Highest-value next hunt.** `neuro/providers.py` — 542 lines of provider
adapters on the recall path, containing every API key in the tier and the
fallback chain that decides which upstream sees a tenant's prompt. It is the
largest unaudited file in the tier and the only one still handling secrets.

### Uncertainty acknowledgment

- **Most likely false positive:** D1. The unit-level violation is real and
  demonstrated, but the consequence is unreachable in the shipped app, so
  calling it a "defect" rather than "a trap someone will spring later" is a
  judgement call. The fix is one function and costs nothing, which is why I
  applied it anyway.
- **Real defect most likely missed:** something in `neuro/providers.py`, or a
  concurrency defect in `TenantManager` more damaging than D3 that I did not
  isolate because I could not drive 100+ concurrent tenants offline.
- **Requires runtime validation:** D3's composition; the actual production value
  of `TOKEN_OPTIMIZATION["context_compression"]`; whether real memory chunks in
  a live tenant contain `/*` often enough that D2 was destroying recall daily
  or only occasionally.
- **What static analysis cannot determine here:** whether `_evict_lru_locked`
  ever selects a tenant with an in-flight request — that depends on request
  duration distribution and tenant cardinality, neither of which is in the code.
- **What would most increase confidence:** production logs from
  `TenantManager` showing eviction frequency and active-tenant high-water mark,
  and a sample of stored `L1`/`L2` bundle contents to measure how often the D2
  trigger substring appears in real memory.

---

## Files changed (uncommitted)

- `src/reasoner/neuro/compression.py` — Fix 1
- `src/reasoner/neuro/cache.py` — Fix 2
- `src/reasoner/hypergate/base_sub_agent.py` — Fix 3
- `tests/test_memory_cache_defects_t7.py` — new, 17 tests
- `docs/reports/defect-hunt-2026-09-01/T7-memory-cache.md` — this report

Not touched: `scripts/ci-local.sh`, `.github/workflows/test.yml`,
`core/parsing.py`, `domain/pipeline_state.py`, `domain/preset_core.py`,
`domain/preset_registry.py` (T6's files).

### Out-of-tier observations (no action taken)

- `hypergate/base_sub_agent.py:34` — the docstring says "Its own class-level
  LRU cache (FIFO eviction)"; `__new__` makes it per-instance. The comment is
  wrong, and it is the comment that makes the dead cache look alive.
- `neuro/sessions.py:88` — `_generate_session_id` derives its suffix from
  `sha256(str(time.time()))`, so two sessions started inside one clock tick
  (~15.6 ms on Windows) get an identical id. Harmless today because session
  files are per-tenant, but it is not the collision resistance the sha256 call
  implies.
- `neuro/sessions.py:198-200` — the per-file lock is taken on
  `self._current_session_file`, and `_write_entry` re-reads that attribute, so
  across a session rollover the lock and the write target can differ.
- `neuro/compression.py:64` — `Language.UNKNOWN` is given C-style comment
  markers. For `/api/neuro/recall`, whose content is always conversational
  prose, comment stripping of any flavour is a guess. Worth revisiting as a
  design decision, separately from Fix 1.
