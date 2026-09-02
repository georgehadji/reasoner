# T4 — LLM Transport & Routing · Autonomous Defect-Hunt Protocol V7

Worktree `.worktrees/defect-hunt`, branch `chore/defect-hunt-t3`. 2026-09-01/02.
Surface: `infrastructure/llm/{registry,router}.py`, `infrastructure/llm/providers/**`,
plus the circuit-breaker call path. Audit budget 12; `budget_spent = 8`.

Evidence tags: **[VF]** verified fact (observable in code, or demonstrated by an executed
test) · **[HYP]** hypothesis · **[UNK]** unknown · **[FALSE]** disproved.

---

## Phase 1 — Defect-surface map

The tier is not "12 adapters each owning transport". It is **one** OpenAI-compatible
provider that every routable model funnels through, plus **four** thin direct-fallback
adapters that only run during an upstream outage. That asymmetry set the hunt order.

| Region | File:function | Classes | Reachability | Blast radius | Invariant density |
|---|---|---|---|---|---|
| R1 | `providers/openai_compat.py:OpenAICompatibleProvider.complete` | 2,3,5 | **REACHABLE** — `asgi:app` / `main.py` / `headless.ask` → `LLMExecutor.execute` → `ProviderRouter.call` → `complete_with_retry` → here | every phase of every run | high (truncation, usage, cost) |
| R2 | `providers/openai_compat.py:__init__` | 5 | REACHABLE — `registry.build_provider` builds a **bare** `OpenAICompatibleProvider` for the xAI-direct, DeepSeek-direct and Ollama lanes; only `OpenRouterProvider` was declaring usage counters | billing + cost caps for three lanes | high |
| R3 | `providers/openai_compat.py:stream_complete` | 2,3 | **DEAD-BUT-PUBLIC** — no production caller: `executor.execute_stream` has zero call sites in `src/`, and `router.call(stream=True)` is reached only from it. Public router API. | any future streaming consumer | medium |
| R4 | `router.py:_execute_stream` | 3,4,5 | DEAD-BUT-PUBLIC (same chain as R3) | contract of the stream generator | medium |
| R5 | `providers/direct.py:{Anthropic,OpenAI,Google}DirectProvider.complete` | 1,2,3 | REACHABLE — `router._execute_call` → `_try_direct_fallback` (`MULTI_PROVIDER_FALLBACK_ENABLED` defaults **true**) | outage path; highest call volume when it runs | low |
| R6 | `router.py:_call_with_circuit` + `_build_metadata` + `_dedupe` | 6,5 | REACHABLE (same as R1) | cost attribution, spend caps, truncation detection | high |
| R7 | `router.py:_resolve_fallback` | 4 | REACHABLE | invariant (c) | high |
| R8 | `registry.py:build_provider` / `_MODEL_WHITELIST` | 4,5 | REACHABLE | routing correctness | high |

Tagged assertions about the map:

- **[VF]** `executor.execute_stream` has no caller in `src/reasoner/**`; `stream=True` appears
  only at `executor.py:668` and `:701`, both inside `execute_stream` itself. The whole
  streaming provider path is therefore unreachable from any entry point today.
- **[VF]** Invariants (b), (c) and (d) are *not* enforced in this tier. Bloc/lab constraints
  live in `infrastructure/llm/constraints/**` and are invoked from
  `application/services/constraint_resolver.py` at preset-resolution time. `ProviderRouter`
  performs no lab or bloc check anywhere.
- **[VF]** The shared shape worth hunting is `providers/direct.py`: four adapters, three of
  which construct a vendor SDK client per call. One shape, three instances.
- **[VF]** `registry._REGISTRY` is a `MappingProxyType` built at import and never mutated;
  `_MODEL_WHITELIST` entries carry no mutable shared state handed to providers. Class 6
  (concurrency) therefore does not apply to the registry — it applies to the *router's*
  process-global `_GLOBAL_RESOLVED_CACHE` and to per-provider `last_*` attributes.

Hunt queue (likelihood × blast_radius × reachability): R1, R2, R6, R5, R3/R4, R7, R8.

---

## Phase 2 — Suspicion generation

| ID | Suspicion | Class | Violated property (named) | Reach | Severity | Prior |
|---|---|---|---|---|---|---|
| D1 | Under any response with `finish_reason="length"`, `openai_compat.py:complete()` never assigns `self.last_finish_reason`, so `router._build_metadata` reports the stale init value `"stop"` and `LLMExecutor._retry_after_truncation` never fires. | 3/5 | *"`finish_reason == "length"` is the only signal that distinguishes a truncated response from a complete one"* — `router.py:456-459`, `executor.py:576-583`, `constants_limits.py:234` | REACHABLE | **high** (silently-wrong result) | high |
| D2 | For the xAI-direct / DeepSeek-direct / Ollama lanes, `build_provider` returns a bare `OpenAICompatibleProvider`, which declares none of `last_input_tokens` / `last_output_tokens` / `last_cost_usd`; `_record_usage`'s `hasattr` guards no-op and `_build_metadata` omits the keys. | 5 | executor cost contract: *"If the provider didn't return a real cost, estimate from token counts"* (`executor.py`, gated on `input_tokens > 0`) | REACHABLE | **high** (billing $0) | high |
| D3 | `openai_compat.py:stream_complete` does `async with self.client.chat.completions.create(...)` without `await`. `AsyncCompletions.create` is an `async def`. | 2 | openai SDK ≥1.x async contract | DEAD-BUT-PUBLIC | high-latent (total failure) | medium |
| D4 | `router.py:_execute_stream` yields the `(text, metadata)` tuple returned by `_try_direct_fallback` into a generator declared `AsyncIterator[str \| DegradedLLMResponse]`. | 5 | `ProviderRouter.call` return-type contract; `executor.execute_stream` `"".join()`s the chunks | DEAD-BUT-PUBLIC | medium | medium |
| D5 | `router.py:_execute_stream` never merges the call-level `extra_body` into the provider, so per-phase reasoning effort is dropped on the streaming path. | 3 | `openai_compat.py:184-187` — *"Dropping it here made every streaming call fall back to the model's default effort — silently spending more tokens than the phase config asked for"* | DEAD-BUT-PUBLIC | medium (silent overspend) | medium |
| D6 | `providers/direct.py` — `AnthropicDirectProvider`, `OpenAIDirectProvider` and `GoogleDirectProvider` each construct an SDK client per `complete()` and never close it. | 1 | transport-ownership: a client the adapter constructs, the adapter must release | REACHABLE | medium-high (pool leak on the outage path) | **high** |
| D7 | `router._build_metadata` reads the provider's `last_*` attributes *after* `_call_with_circuit` released the per-model semaphore, while `_dedupe` shares one provider instance process-wide. | 6/5 | per-call metadata must describe *that* call | REACHABLE | **high** (cost/token/truncation cross-wiring) | high |
| D8 | `OpenAIDirectProvider` sends `max_tokens` and `temperature` for its default model `gpt-5.5`. | 2 | this repo's own `OpenAICompatibleProvider._uses_completion_tokens()` and `_FIXED_TEMPERATURE_MARKERS` | REACHABLE | medium | high |
| D9 | `GoogleDirectProvider` calls `genai.aio.Client(...)`; google-genai exposes no `aio` module. | 2 | google-genai API surface | REACHABLE | medium (lane permanently dead, failure swallowed into `continue`) | — (found during D6 innocence work) |
| D10 | `_resolve_fallback` filters only on `p.model != assigned.model`; a role with no explicit fallback falls back to `primary` with no lab/bloc check. | 4 | invariant (c) *"fallbacks fail to a cross-lab equivalent, never blindly to preset primary"* | REACHABLE | medium | medium |

---

## Phase 3 — Proof of defect

All fakes sit at a transport boundary. `httpx.MockTransport` under a **real**
`openai.AsyncOpenAI` for everything routed through `OpenAICompatibleProvider` (the
provider, the router and the SDK's own request/response plumbing all execute for real);
the vendor SDK *constructor* for `providers/direct.py`, which builds its client internally
and offers no injection point. **No test in this hunt makes a network call.** Proofs live
in `tests/test_defect_hunt_t4_llm_transport.py`.

### D1 — finish_reason lost on the non-streaming path
- **Trigger: FIRED.** `test_complete_records_finish_reason_length` — transport returns
  `finish_reason: "length"`; `provider.last_finish_reason` reads `"stop"`.
  `AssertionError: assert 'stop' == 'length'`. Same through the router:
  `test_router_metadata_surfaces_truncation`.
- **Innocence: NO-DEFENSE-FOUND.** `grep last_finish_reason` returns exactly three writers —
  `stream_complete` (:190), `call_with_tools` (:350), `OpenRouterProvider.__init__` (:416).
  `complete()` is absent. Nothing else derives truncation.
- **Verdict: CONFIRMED.**

### D2 — direct lanes report no tokens and no cost
- **Trigger: FIRED.** `test_direct_lane_provider_reports_token_usage` →
  `AttributeError: 'OpenAICompatibleProvider' object has no attribute 'last_input_tokens'`.
  Through the router: `test_direct_lane_metadata_enables_cost_estimation` →
  `assert 0 > 0` (key absent from metadata).
- **Innocence: NO-DEFENSE-FOUND.** `_record_usage` is `hasattr`-guarded and
  `_build_metadata` is `hasattr`-guarded, so the omission is total and silent. The
  executor's estimator is gated on `input_tokens > 0`, so the run bills at $0 and spend
  ceilings never engage on these lanes. Note this is *not* a caller defect: `build_provider`
  itself chooses the bare class (`case "compat"`, and the xAI/DeepSeek direct branches).
- **Verdict: CONFIRMED.**

### D3 — `stream_complete` never awaits the SDK coroutine
- **Trigger: FIRED.** `test_stream_complete_works_against_the_real_sdk` →
  `openai_compat.py:182: TypeError: 'coroutine' object does not support the asynchronous
  context manager protocol`, plus `RuntimeWarning: coroutine 'AsyncCompletions.create' was
  never awaited`. openai 1.109.1.
- **Innocence: NO-DEFENSE-FOUND — and the existing test actively concealed it.**
  `tests/test_prompt_caching.py::test_stream_complete_forwards_extra_body_and_temperature_rules`
  stubs `create` as a **sync** function returning an async context manager, which is not the
  SDK's shape. That is why 3946 green tests coexist with a method that cannot run.
- **Reachability caveat [VF]:** no production caller today (see Phase 1). Ranked as
  high-latent, not critical.
- **Verdict: CONFIRMED.**

### D4 / D5 — stream contract and dropped `extra_body`
- **Trigger: DID-NOT-FIRE (no executable trigger built).** Both are read from code:
  `router.py` yields `direct` (a 2-tuple) at the direct-fallback branch, and
  `_execute_stream` references `extra_body` only when forwarding to `_try_direct_fallback`,
  never when calling `provider.stream_complete_with_retry`. Reaching either requires the
  D3-broken streaming path plus a primary+fallback double failure plus a live direct key.
- **Innocence: NO-DEFENSE-FOUND** (code-read).
- **Verdict: CONFIRMED by inspection, severity discounted for DEAD-BUT-PUBLIC reachability.**
  Fixed anyway — both are one- and eight-line changes on a path that will be revived the
  moment D3 is fixed.

### D6 — direct-fallback adapters leak their transport
- **Trigger: FIRED, all three.** `test_direct_fallback_adapter_closes_its_client` →
  `AnthropicDirectProvider leaked its transport client`, same for `OpenAIDirectProvider`
  and `GoogleDirectProvider`. Error path too:
  `test_direct_fallback_adapter_closes_client_on_error`.
- **Innocence attempt — ownership checked, as required.** These adapters are *not* handed a
  client: each calls the constructor itself inside `complete()`, and
  `_try_direct_fallback` builds a fresh provider per call, so nothing above them can own or
  close it. `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI` both expose `__aenter__`
  **[VF]**, so closure was available and unused. Contrast `OpenAICompatibleDirectProvider`
  in the same file, which *does* use `async with httpx.AsyncClient(...)` — CODE-INNOCENT,
  cleared.
- **Verdict: CONFIRMED for Anthropic + OpenAI. For Google, CLEARED-as-leak** — `genai.Client`
  has no close method **[VF]** — but see D9.

### D7 — per-call metadata races on a process-shared provider
- **Trigger: STATISTICAL(99/120 = 82.5%).** `test_concurrent_calls_do_not_crosswire_usage_metadata`:
  120 concurrent `router.call`s, transport echoes the request's `max_tokens` as both the
  response body and `usage.prompt_tokens`; 99 calls received a *different* call's counters.
- **Mechanism [VF]:** `_call_with_circuit` releases the per-model semaphore (default limit
  **30**, not 1) before `_execute_call` invokes `_build_metadata`, and `_dedupe` hands every
  router the same provider instance for a given (class, model, credential, extra_body) key.
  So `last_input_tokens` / `last_cost_usd` / `last_finish_reason` are read after another
  call may have overwritten them.
- **Innocence: NO-DEFENSE-FOUND.** The semaphore is a throughput bound, not a mutex; its own
  docstring says so.
- **Verdict: CONFIRMED (statistical).** Not fixed — see Phase 5.

### D8 — `OpenAIDirectProvider` sends parameters its own default model rejects
- **Trigger: FIRED.** `test_openai_direct_respects_the_repo_parameter_rules` →
  `assert 'max_tokens' not in {'max_tokens': 256, ..., 'model': 'gpt-5.5', 'temperature': 0.2}`.
  The same test first asserts, against this repo's own code, that
  `_uses_completion_tokens()` is `True` and `_supports_temperature()` is `False` for
  `gpt-5.5` — so this is an internal-contract violation **[VF]**, not a vendor claim.
  Whether OpenAI actually 400s on it is **[HYP]** (unverifiable without a live call).
- **Innocence: NO-DEFENSE-FOUND.**
- **Verdict: CONFIRMED.**

### D9 — the Google fallback lane has never worked
- **Trigger: FIRED** (surfaced while proving D6): `module 'google.genai' has no attribute
  'aio'` — google-genai 1.2.0 exposes the async surface as `Client(...).aio`, not
  `genai.aio.Client(...)` **[VF]**.
- **Innocence: NO-DEFENSE-FOUND.** `_try_direct_fallback` catches `Exception`, logs a
  warning, and `continue`s — so the lane's permanent death is indistinguishable from a
  transient provider failure. This is the "failure swallowed so it looks like something
  else" shape T1 confirmed, in a second location.
- **Verdict: CONFIRMED.**

### D10 — no cross-lab guard in the router's fallback
- **Trigger: DID-NOT-FIRE.** `_resolve_fallback` demonstrably applies no lab/bloc check
  **[VF]** — but that does not by itself violate invariant (c), because the cross-bloc
  constraints are enforced upstream at preset resolution
  (`application/services/constraint_resolver.py` + `constraints/{bloc_diversity,no_repeat_lab}.py`),
  which is outside this tier.
- **Innocence: CODE-INNOCENT at this layer.** The residual concern is narrower and stays
  **[UNK]**: for a role with *no* explicit `fallback_routing` entry, the router falls back to
  `primary`, and whether every preset supplies an explicit cross-bloc fallback for every
  role is a `domain/preset_registry.py` question this tier cannot answer.
- **Verdict: INDETERMINATE — out-of-tier observation, handed to whoever owns `domain/`.**

---

## Phase 4 — Triage inventory

Ranked by severity × reachability × blast_radius.

| # | Candidate | Trigger | Innocence | Evidence basis | Status |
|---|---|---|---|---|---|
| D1 | `complete()` never records `finish_reason` | FIRED | NO-DEFENSE-FOUND | executed test at httpx boundary + exhaustive writer grep | **CONFIRMED — FIXED** |
| D2 | bare compat provider reports no usage/cost | FIRED | NO-DEFENSE-FOUND | executed test + `build_provider` branch read | **CONFIRMED — FIXED** |
| D7 | concurrent calls cross-wire usage metadata | STATISTICAL(99/120) | NO-DEFENSE-FOUND | executed 120-trial harness | **CONFIRMED — NOT FIXED** |
| D6 | Anthropic/OpenAI direct adapters leak transport | FIRED | ownership checked, adapter-owned | executed test, success + error path | **CONFIRMED — FIXED** |
| D9 | Google fallback lane calls a non-existent API | FIRED | NO-DEFENSE-FOUND | executed test + installed-SDK introspection | **CONFIRMED — FIXED** |
| D3 | `stream_complete` missing `await` | FIRED | existing test concealed it | executed test at httpx boundary | **CONFIRMED — FIXED** |
| D8 | direct OpenAI sends gpt-5-invalid params | FIRED | NO-DEFENSE-FOUND | executed test asserting against repo's own predicates | **CONFIRMED — FIXED** |
| D4 | stream yields a tuple | DID-NOT-FIRE | NO-DEFENSE-FOUND | code read | **CONFIRMED (inspection) — FIXED** |
| D5 | stream drops call-level `extra_body` | DID-NOT-FIRE | NO-DEFENSE-FOUND | code read + in-repo comment naming the consequence | **CONFIRMED (inspection) — FIXED** |
| D10 | router fallback has no cross-lab guard | DID-NOT-FIRE | CODE-INNOCENT at this layer | code read | **INDETERMINATE — out of tier** |
| — | `OpenAICompatibleDirectProvider` transport | n/a | CODE-INNOCENT (`async with`) | code read | **CLEARED** |
| — | `_dedupe` conflating two tenants' providers | n/a | CODE-INNOCENT — identity includes `secret_digest(api_key)` and `base_url` | code read + `routing_identity` | **CLEARED** |
| — | `_REGISTRY` mutation under concurrency | n/a | CODE-INNOCENT — `MappingProxyType`, built at import | code read | **CLEARED** |
| — | `close_shared_pool` double-close | n/a | CODE-INNOCENT — `_pool_closed` flag under a lock | code read | **CLEARED** |

Cleared: 4. Confirmed: 9 (8 fixed, 1 deferred). Indeterminate: 1.

---

## Phase 5 — Fix design

Fixes are in priority order. Every one is ≤15 lines and ≤1 function unless flagged.

### Fix 1 (D1) — record the truncation signal · `providers/openai_compat.py:complete()`

```diff
         self._record_usage(getattr(response, "usage", None))
+        # finish_reason == "length" is the only signal that separates a response
+        # cut off at max_tokens from a complete one once content collapses to a
+        # string. Only stream_complete()/call_with_tools() recorded it, so every
+        # non-streaming call — i.e. the whole pipeline — reported a stale "stop"
+        # and LLMExecutor._retry_after_truncation could never fire.
+        self.last_finish_reason = response.choices[0].finish_reason or "stop"
         return response.choices[0].message.content or ""
```

**Causal justification.** The mechanism is "the value is never written on this path".
Writing it at the single point where the response is in hand breaks that, and matches
`call_with_tools`'s existing `or "stop"` normalisation exactly.
**Risk.** Scope: one attribute on one path. Side effects: `_retry_after_truncation` now
actually fires for JSON-contract roles — that is the intended behaviour and it is
budget-bounded by `TRUNCATION_RETRY_MAX_TOKENS`, but it *will* increase spend on runs that
were previously silently truncating. Regression: none observed. Reversible: one line.

### Fix 2 (D2) — declare usage counters on the shared base · `openai_compat.py:__init__`

```diff
         self.last_cache_read_tokens: int = 0
         self.last_cache_write_tokens: int = 0
+        # Per-call usage counters, declared here rather than on OpenRouterProvider
+        # alone: build_provider() returns a *bare* OpenAICompatibleProvider for the
+        # xAI-direct, DeepSeek-direct and Ollama lanes. Without these attributes
+        # _record_usage's hasattr guards silently no-op and _build_metadata omits
+        # the keys entirely, so those lanes reported zero tokens — which also
+        # disables LLMExecutor's "estimate cost from token counts" fallback and
+        # bills the run at $0.
+        self.last_input_tokens: int = 0
+        self.last_output_tokens: int = 0
+        self.last_cost_usd: float = 0.0
+        self.last_finish_reason: str = "stop"
```

**This is the shared-base fix the protocol asks for.** One change in
`OpenAICompatibleProvider` covers `OpenRouterProvider`, `FineTunedProvider`, and the three
bare-compat lanes; the alternative was per-lane patching at three `build_provider`
branches. It also makes Fix 1 total rather than OpenRouter-only. A duplicated
`self.last_finish_reason = "stop"` line in `OpenRouterProvider.__init__` was deleted as
dead.
**Risk.** `_build_metadata` now emits `input_tokens`/`output_tokens`/`cost_usd`/`finish_reason`
where it previously omitted them. Every consumer read them via `.get(..., 0)` or `.get(..., 0.0)`
already, so present-and-zero is identical to absent. Reversible.

### Fix 3 (D3) — await the SDK coroutine · `openai_compat.py:stream_complete`

```diff
-        async with self.client.chat.completions.create(**kwargs) as response:
+        async with await self.client.chat.completions.create(**kwargs) as response:
```

Plus a companion test correction — `tests/test_prompt_caching.py`'s `_FakeCompletions.create`
becomes `async def`, because a sync stub is not the SDK's shape and is precisely what hid
this. **Risk.** Any other test stubbing `create` synchronously will now fail; a search of
`tests/` found only this one. Reversible.

### Fix 4 (D6) — release the transport · `providers/direct.py`, two adapters

`AnthropicDirectProvider.complete` and `OpenAIDirectProvider.complete` each wrap their
client construction in `async with`, so success *and* exception paths release the pool.

```diff
-            client = AsyncAnthropic(api_key=self._api_key, timeout=TIMEOUTS.LLM_CALL)
-            response = await client.messages.create(...)
+            async with AsyncAnthropic(
+                api_key=self._api_key, timeout=TIMEOUTS.LLM_CALL
+            ) as client:
+                response = await client.messages.create(...)
             return response.content[0].text
```

`[REQUIRES HUMAN REVIEW: repeated across two adapter functions]` — the protocol's
one-function limit. There is **no shared base to fix once**: `AnthropicDirectProvider`,
`OpenAIDirectProvider` and `GoogleDirectProvider` are siblings under `BaseLLMProvider` with
nothing in common but the interface, and introducing a base class to host client lifecycle
would be a larger and riskier diff than two mechanically identical `async with`s. Flagging
rather than escalating.
**Risk.** Both SDKs expose `__aenter__` (verified against the installed versions), and
`__aexit__` closes rather than cancels in-flight work, which has already completed by then.
Regression risk low; reversible per adapter.

### Fix 5 (D8) — use the parameter names the model accepts · `OpenAIDirectProvider.complete`

Reuses this repo's own predicates rather than restating the rules:

```diff
+            probe = _Compat.__new__(_Compat)
+            probe.model = self.model
+            if probe._uses_completion_tokens():
+                kwargs["max_completion_tokens"] = max_tokens
+            else:
+                kwargs["max_tokens"] = max_tokens
+            if probe._supports_temperature():
+                kwargs["temperature"] = temperature
```

**Causal justification.** The mechanism is "two facts encoded in one class, unknown to its
sibling". Importing the predicates removes the duplication instead of forking it, so a
future model added to `_FIXED_TEMPERATURE_MARKERS` fixes both call sites at once.
**Risk.** `__new__` + attribute assignment sidesteps `_Compat.__init__` deliberately (it
builds a client); both predicates read only `self.model`. Slightly unusual, and marked as
such. Non-gpt-5 models keep the classic parameter names — covered by a no-regression test.

### Fix 6 (D9) — call the API that exists · `GoogleDirectProvider.complete`

`genai.aio.Client(...)` → `genai.Client(...)` then `await client.aio.models.generate_content(...)`.
No context manager: `genai.Client` exposes no close method, so there is nothing to release.
**Risk.** This turns a lane that always raised into one that issues a real request. If the
lane is misconfigured in production it will now fail differently (auth/quota) rather than
with an AttributeError — that is an improvement, but it is a behaviour change on the outage
path. Reversible.

### Fix 7 (D4) — yield a chunk, not a tuple · `router.py:_execute_stream`

```diff
-                        yield direct
+                        yield direct[0]
```

### Fix 8 (D5) — merge call-level `extra_body` on the streaming path · `router.py:_execute_stream`

Save/merge/restore around the `async for`, inside the existing `async with semaphore`,
mirroring `_call_with_circuit` exactly.

**Fix interactions.** Fix 2 is a precondition for Fix 1 being total (it supplies the
attribute on the bare lanes). Fixes 3, 7 and 8 all sit on the same streaming path and only
matter together — 3 makes it run at all, 7 makes its output well-typed, 8 makes it honour
the phase's reasoning effort. Fixes 4 and 5 touch the same function
(`OpenAIDirectProvider.complete`) and were written as one edit. No fix touches `registry.py`
or the whitelist, so nothing here can change model routing.

### D7 — NOT FIXED · `[REQUIRES HUMAN REVIEW: cross-boundary mechanism]`

The minimal causal fix is to snapshot the counters while the semaphore is still held. That
changes `_call_with_circuit`'s return type and both of its call sites — three functions,
across the helper/router boundary, in a file two other agents are editing this session.
Diff written out, deliberately not applied:

```diff
-        result = await asyncio.wait_for(coro, timeout=effective_timeout)
-        await circuit.record_success()
-        return result
+        result = await asyncio.wait_for(coro, timeout=effective_timeout)
+        # Snapshot inside the critical section: _dedupe shares one provider
+        # instance process-wide and the semaphore permits 30 concurrent calls,
+        # so these attributes belong to whichever call touched them last by the
+        # time the caller reads them.
+        usage = {k: getattr(provider, k) for k in (
+            "last_input_tokens", "last_output_tokens", "last_cost_usd",
+            "last_finish_reason", "last_cache_read_tokens", "last_cache_write_tokens",
+        ) if hasattr(provider, k)}
+        await circuit.record_success()
+        return result, usage
```

…with `_attempt_call_and_record` unpacking the pair and `_build_metadata` taking the
snapshot dict instead of the live provider. The proof-of-defect test is retained as
`xfail(strict=True)`, so it converts into a failure the day someone fixes this.

---

## Phase 6 — Self-review (RAR)

| Fix | Boundary | Invalid input | State | Regression | Concurrency | New defect | Verdict |
|---|---|---|---|---|---|---|---|
| 1 (finish_reason) | `finish_reason: null` → `"stop"`, covered by test | `choices` already validated non-empty two lines above | writes one attribute, no ordering dependence | 48 neighbouring tests pass | inherits D7's shared-instance hazard — **does not create it**, and the value was unconditionally wrong before | none | **FIX HOLDS [VF]** |
| 2 (counters) | absent `usage` → zeros, covered by test | non-numeric `usage` fields → `or 0` in `_record_usage`, unchanged | pure initialisation | metadata gains keys consumers already `.get()` with defaults | same as above | none | **FIX HOLDS [VF]** |
| 3 (`await`) | empty stream covered by test | mid-stream transport error still propagates to `stream_complete_with_retry` unchanged | none | one concealing test corrected; no other sync `create` stub in `tests/` | none | none | **FIX HOLDS [VF]** |
| 4 (`async with`) | error path covered by test | n/a | client is function-local | both SDKs expose `__aenter__`, verified against installed versions | fresh client per call, nothing shared | none | **FIX HOLDS [VF]** |
| 5 (gpt-5 params) | legacy model keeps `max_tokens`/`temperature`, covered by no-regression test | `self.model` is always a str | `probe` is a throwaway | fallback path only | none | `__new__` bypasses `__init__` — safe because both predicates read `self.model` only, but it is the one clever line here | **FIX HOLDS [VF]** |
| 6 (google API) | `response.text` → `or ""` unchanged | `ImportError` branch unchanged | none | the lane could not previously succeed, so there is no working behaviour to regress | none | untested against a live Google key | **FIX HOLDS [HYP]** — API shape verified against installed google-genai 1.2.0 **[VF]**; end-to-end success is **[UNK]** |
| 7 (`direct[0]`) | `direct` is `None`-checked immediately above | n/a | none | no production caller | none | none | **FIX HOLDS [VF]** |
| 8 (stream extra_body) | `extra_body=None` → untouched | provider without `extra_body` → `hasattr` guard | `try/finally` restores the original, including on generator close | no production caller | mutates shared provider state — **the same known hazard `_call_with_circuit` already has (D7)**, inside the same semaphore, and strictly better than the unconditional wrong value | mutation window on a shared instance | **FIX HOLDS [HYP]** — correct single-caller [VF]; under concurrency it inherits D7 |

No fix reached the FIX BREAKS state, so no revise-once cycle was needed.

---

## Phase 7 — Tests

`tests/test_defect_hunt_t4_llm_transport.py` — 16 tests: 7 proof-of-defect (fail without
the fix, pass with it), 6 boundary, 3 no-regression, 1 `xfail(strict=True)` holding D7 open.

```
15 passed, 1 xfailed in 188.39s
```

Neighbouring suites, unchanged behaviour:

```
tests/test_prompt_caching.py tests/test_multi_provider.py
tests/test_provider_router_degradation.py tests/unit/test_truncation_retry.py
tests/test_defect_hunt_fixes.py tests/test_llm_cancelled_error.py
  → 48 passed in 226.61s

tests/test_openrouter.py
  → 23 passed in 127.57s
```

A harness note worth recording: the first draft of this suite reused `api_key="k"` across
tests and several assertions read the *wrong provider*. `ProviderRouter._dedupe` keys on
`(class, model, base_url, secret_digest(api_key), extra_body)` and caches process-wide, so
identical construction arguments in two tests return one shared instance. Each test now
uses a distinct key. The cache itself is sound — the digest and base URL are in the key, so
two tenants cannot collide — but it is a live cross-test hazard.

### Gate status

- **ruff ratchet moved and I did not touch the constant.** `scripts/ruff_ratchet.py --max 2249`
  now reports **2247**, and fails *because debt was paid down*. Measured per file against
  `HEAD`: my changes account for exactly **−1** (an `E501` in `direct.py:131` — the long
  `genai.aio.Client(...)` line, reformatted by Fix 6). The other **−1** came from a
  concurrent agent's edit elsewhere in `src/`. Per the hazard note this is reported, not
  edited. Whoever lands these changes must lower `--max` to the then-current count in
  **both** `scripts/ci-local.sh:51` and `.github/workflows/test.yml`.
- **import-linter:** `Contracts: 1 kept, 0 broken` — unchanged. No fix inverts the
  infrastructure→ports direction.

### Files changed

```
src/reasoner/infrastructure/llm/providers/direct.py         (+ ~50 / − ~15)
src/reasoner/infrastructure/llm/providers/openai_compat.py  (+ 21 / − 3)
src/reasoner/infrastructure/llm/router.py                   (+ 24 / − 5)
tests/test_prompt_caching.py                                (+ 5 / − 1)   test-fake correction
tests/test_defect_hunt_t4_llm_transport.py                  (new)
docs/reports/defect-hunt-2026-09-01/T4-llm-transport.md      (new, this file)
```

Nothing committed or pushed.

---

## Phase 8 — Verdict, coverage and residual risk

**Audited.** `providers/openai_compat.py` (both classes, all four call methods, shared-pool
lifecycle) · `providers/direct.py` (all four adapters + `build_fallback_provider`) ·
`router.py` (call, stream, tool-call, fallback resolution, dedupe, semaphores, telemetry) ·
`registry.py` (`_MODEL_WHITELIST` shape, `build_provider` branches, `_vendor_of`/`bloc_of`,
`MappingProxyType` freeze) · the circuit-breaker *call sites* in `_call_with_circuit`.

**NOT audited — name the gaps.**
- `providers/finetuned.py` (`FineTunedProvider`) — read, never exercised. It inherits every
  fix above; nothing specific to it was tested.
- `providers/noop.py` — read only. Note it subclasses a *different* `BaseLLMProvider` (from
  `llm/ports.py`, not `llm/base.py`) and implements `_complete_impl`, not `complete`. Two
  base classes with the same name is a trap; not pursued.
- `infrastructure/llm/{image_generation,image_model_catalogue,capability_registry,caching,pricing_resolver,spend_tracker,executor}.py` —
  `executor.py` was read only where it consumes router metadata.
- `circuit_breaker.py` internals — `can_execute()` / `record_failure()` atomicity and the
  Redis/Valkey Lua paths were **not** examined. The check-then-act shape at
  `_call_with_circuit:134` is visible but unproven.
- The **12-adapter claim in the census is inaccurate for this tier**: there are two
  concrete transport classes (`OpenAICompatibleProvider`, `OpenAICompatibleDirectProvider`)
  and three SDK adapters. "Anthropic, Perplexity, DeepSeek, Mistral, xAI, Qwen, Kimi, GLM,
  MiniMax, Ollama" are registry *entries*, not distinct adapters. No per-vendor adapter went
  unexamined because no per-vendor adapter exists.

**Classes covered.** 1 resource lifecycle ✓ · 2 contract/dependency ✓ · 3 error paths ✓ ·
4 routing correctness — partial (invariant enforcement is out of tier) · 5 type/serialization ✓ ·
6 concurrency — partial (provider state proven; circuit-breaker atomicity not).

**Confirmed by severity.** High: D1, D2, D7. Medium-high: D6, D9, D3(latent). Medium: D8,
D4, D5. **Cleared:** 4. **Residual UNKNOWN:** D10's per-preset fallback question; whether
D9's fix succeeds against a live Google key; circuit-breaker atomicity; the streaming path's
behaviour once it acquires a real caller.

**Clean-claim scope — deliberately narrow.** I claim only this: *on the non-streaming
OpenAI-compatible path, truncation is now signalled and usage is now recorded for all four
provider lanes, and the two SDK-backed direct-fallback adapters no longer leak a connection
pool per call.* I do **not** claim the transport layer is sound. One confirmed high-severity
defect (D7) is knowingly unfixed, the streaming path has never had a production caller and
therefore has never been exercised end-to-end, and the circuit breaker was not opened.

**Highest-value next hunt.** D7's fix, then `circuit_breaker.py` internals — it sits in
every LLM call, `can_execute()`/`record_failure()` are `await`ed across a suspend point in
`_call_with_circuit`, and the same shared-mutable-state pattern that produced an 82.5%
cross-wiring rate in D7 is present there by construction.

### Uncertainty acknowledgment

- **Most likely false positive: D5** (streaming drops `extra_body`). It has no production
  caller, so "silent overspend" describes a path nothing takes. If `execute_stream` is
  intentionally abandoned rather than pending, D5, D4 and much of D3's severity evaporate.
  D8 is the runner-up: I proved an internal-contract violation, not a vendor 400.
- **Defect most likely missed:** a `finish_reason`/usage-shape assumption specific to a
  non-OpenAI vendor routed through OpenRouter. Every proof used one synthetic
  OpenAI-shaped payload; a vendor that reports `finish_reason: "max_tokens"` or nests usage
  differently would defeat Fix 1 silently, exactly as the original defect did. Second-most
  likely: a circuit-breaker state race.
- **Needs runtime validation:** that Fix 6 actually reaches Google; that Fix 1 does not cause
  a spend spike once truncation retries start firing on real traffic (they have been dead
  since the feature shipped); that Fix 3 works against a live streaming endpoint rather than
  a synthetic SSE body.
- **What static analysis cannot determine here:** real vendor response shapes,
  429/5xx/`Retry-After` behaviour, whether `keepalive_expiry=120s` matches any upstream's
  idle timeout, and the actual concurrency the pipeline drives per model — which is what
  turns D7 from an 82.5% laboratory rate into a production number.
- **Input that would most increase confidence:** a captured corpus of real OpenRouter
  responses per vendor (headers, `usage`, `finish_reason`, error bodies) to replay through
  `MockTransport`. Second: an answer to whether `LLMExecutor.execute_stream` is dead code or
  a pending integration — that single fact re-ranks four of the nine confirmed defects.
