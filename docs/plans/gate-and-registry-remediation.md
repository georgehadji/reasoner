# Gate & Registry Remediation Plan

**Created:** 2026-08-29
**Branch at time of writing:** `studio-adopt` @ `7844682`
**Scope:** the ten problems left standing after the HyperGate SSOT work of
2026-08-28/29. Three are live correctness or safety defects; the rest are
structural debt that caused them and will cause them again.

**Prerequisite reading:** `docs/plans/hypergate-routing-ssot.md` (the findings
this plan discharges), `CLAUDE.md` §5 (invariants), `docs/adr/001` (hexagonal),
`docs/adr/003` (HyperGate).

---

## 0. How to use this document

Each workstream is self-contained: problem with evidence, the design and why
that design, ordered steps, tests, a verification command that must pass, and a
rollback. Workstreams are ordered by dependency in §12, not by number.

Every claim of fact below is labelled:

- **VERIFIED** — measured or read directly in this repo on 2026-08-29.
- **INFERENCE** — follows from verified facts but not itself observed.
- **HYPOTHESIS** — plausible, must be confirmed before the work depends on it.
- **UNKNOWN / [INPUT REQUIRED: …]** — needs a decision or a measurement first.

---

## 1. Safety rules — binding on every workstream

These exist because this codebase has already been bitten by each of them.

**S1. Never change a name and a behaviour in the same commit.**
`MODEL_GEMINI_FLASH` was repointed at `grok-4.3` without renaming; the resulting
entry collided with the literal `"grok-4.3"` key, the later key won, and the
registry silently held one fewer model (recorded in `registry.py`'s own
comments). A rename commit must prove byte-identical behaviour; a behaviour
commit must not touch names.

**S2. Every behavioural change carries a before/after snapshot.**
The pattern already used and proven in `08c6993`:

```python
# capture resolved routing for all 49 presets x every slot, diff after
snap[p.id][f"routing.{role}"] = resolved_model_of(model_id)
```

For non-routing changes the equivalent is a recorded measurement (latency
histogram, parse-success count) taken before and after, in the same session.

**S3. No model may be routed anywhere on catalogue metadata alone.**
`_supports_json_mode()` trusted the OpenRouter catalogue's
`supported_parameters`; two models that advertise structured-output support
return `-1.0000000000000002e+308` and `""` under it. Probe the actual model with
the actual prompt before routing it. `_JSON_MODE_DENYLIST` and
`_FIXED_TEMPERATURE_MARKERS` are the established shape for recording the
result.

**S4. Kill switches for anything that changes outbound request shape.**
`LLM_JSON_MODE_ENABLED` is the precedent: a settings flag that disables the new
behaviour without a redeploy. Anything altering what we send to a provider gets
one.

**S5. The four propagation-resistance invariants are untouchable.**
`CLAUDE.md` §5: recalled memory never enters a system prompt; Phase-2 generators
stay blind to each other; `harden_system_prompt()` stays applied at the two
application chokepoints; model- and web-authored text stays wrapped. W4 and W5
both touch HyperGate; neither may weaken these. HyperGate's documented exclusion
from `harden_system_prompt()` is deliberate — see the note at
`base_sub_agent._llm_call` — and stays.

**S6. Layer discipline is not negotiable, and the port is the fix.**
`application/` and `domain/` must not import `infrastructure.llm.registry`.
When application code needs a registry fact, the answer is to extend
`core/ports/model_registry_port.py`, never to add an import. `.importlinter`
holds at 60 exceptions / MAX 65; no workstream may raise it.

**S7. Deleting dead code is preferred to fixing it.**
A dead class that is "fixed" reads as live and drifts again. If it is not
reachable, delete it.

**S8. Gates must move in lockstep, in both directions.**
`ruff_ratchet.py` and `count_importlinter_exceptions.py` fail on `<` as well as
`>`. Any workstream that changes the count updates MAX in the same commit,
in both `scripts/ci-local.sh` and `.github/workflows/test.yml`.

---

## 2. W1 — Retire the stale `style_brief` tests

**Priority:** first. Everything else is measured against a green baseline.
**Risk:** minimal. Test-only.

### Problem (VERIFIED)

Three tests fail, confirmed still failing at `80e36b8` in a clean detached
worktree, i.e. they predate all of this work:

```
tests/test_article_adapters.py::TestContextConversion::test_style_brief_preserved
tests/test_article_golden_set.py::...::test_style_brief_integration[styled_newyorker]
tests/test_article_golden_set.py::...::test_style_brief_integration[styled_financial]
```

`rg 'style_brief' src/` returns **nothing**. The key exists only in tests. And
the suite contradicts itself: `tests/test_article_pipeline_regression.py:264`
is `test_draft_prompt_ignores_style_brief`, whose docstring reads *"style_brief
is inert: nothing in production ever wrote the key."*
`tests/test_writing_sot_prompts.py:4` refers to "style_brief removal".

So a deliberate feature removal left three assertions behind that test the
removed behaviour, while a fourth test asserts the removal held.

### Design

Delete, do not repair. Per **S7**: the production code is correct; the tests
encode a feature that was intentionally taken out. Repairing them would mean
re-adding `style_brief` to the writing state, which nothing asked for.

Keep `test_draft_prompt_ignores_style_brief` — it is the regression guard that
the key stays inert, and it is the reason we know the removal was intentional.

### Steps

1. Delete `TestContextConversion::test_style_brief_preserved` from
   `tests/test_article_adapters.py`, and the now-unused `style_brief` kwarg
   path in its `_make_test_ctx` helper if nothing else uses it.
2. In `tests/test_article_golden_set.py`: delete
   `test_style_brief_integration`, the `style_brief` field on
   `ArticleTestCase` (line ~58), the two fixtures that set it (~184, ~192), the
   `ws["style_brief"] = tc.style_brief` write (~329), and the
   `"has_style_brief"` key emitted into the baseline (~613).
3. Regenerate `tests/_data/article_baseline.json` if step 2 changes its shape —
   it currently carries `"has_style_brief": false` twice. Confirm whether that
   file is generated or hand-maintained before editing.
4. Add a one-line comment at `test_draft_prompt_ignores_style_brief` pointing
   at this removal, so the next reader knows the sibling tests were retired on
   purpose rather than lost.

### Verification

```bash
python -m pytest tests/test_article_adapters.py tests/test_article_golden_set.py tests/test_article_pipeline_regression.py tests/test_writing_sot_prompts.py -q
```

Full suite must go from `5 failed, 3927 passed` to `0 failed`.

### Rollback

Revert the commit. No production code touched.

---

## 3. W2 — Delete the dead `GateAgent`

**Priority:** early, trivial, removes a trap.
**Risk:** low, but see the shim caveat.

### Problem (VERIFIED)

`rg 'GateAgent\('` matches nothing outside `HyperGateAgent`. The class at
`src/reasoner/hypergate/gate_agent.py:132-242` is never instantiated. It
carries:

- the same `role="primary"` bug fixed in `e241bb8` for the live path
  (`gate_agent.py:170`),
- the same `is_openai` sniff deleted in `e241bb8` (`gate_agent.py:157,163`),
- a second `_TAXONOMY` that has drifted from the live one in
  `sub_agents/method_classifier.py:26` — its `"F"` is `iterative` where the live
  map says `jury`, and it is missing `R`/`S`/`T`/`U`.

A reader fixing a routing bug will find two taxonomies and no signal as to
which is authoritative.

### Design

Delete the class only. `GateDecision` in the same module **must stay** — it is
imported by `hypergate/__init__.py:1`, `hypergate/hyperagent.py:26`, and three
tests, and re-exported by the backward-compat shim `src/reasoner/gate_agent.py`.

Do **not** move `GateDecision` to `hypergate/models.py` in this commit even
though that is where `SubAgentInput`/`SubAgentOutput` live and where it
arguably belongs. That is a second, independent change (**S1**) and it touches
the public shim. File it as a follow-up.

### Steps

1. Delete `class GateAgent` and its module-level `_TAXONOMY`, plus any imports
   (`GATE_MAX_TOKENS`, `GATE_TEMPERATURE`, `GATE_TIMEOUT_SECONDS`) left unused.
2. `GATE_TIMEOUT_SECONDS` is still read by `orchestrator.py:288`
   (`_gate_timeout = max(GATE_TIMEOUT_SECONDS * 2, 5.0)`) — **VERIFIED**, so the
   constant stays in `constants_limits.py`. Check `GATE_MAX_TOKENS` /
   `GATE_TEMPERATURE` / `GATE_CONFIDENCE_THRESHOLD` for remaining readers before
   deleting any of them.
3. Update the module docstring so it describes a decision type, not an agent.
4. Grep `docs/` for references to `GateAgent` as a live component and correct
   them.

### Verification

```bash
rg -n 'GateAgent' src/ tests/ docs/
python -m pytest tests/test_hypergate.py tests/test_api_gate.py tests/test_reliability_patches.py tests/test_preflight_gate_isolation.py -q
python scripts/ruff_ratchet.py --max <new>   # deletion lowers the count; S8 applies
```

### Rollback

Revert. The class had no callers, so nothing can regress at runtime.

---

## 4. W3 — Give the gate a real deadline

**Priority:** HIGH. This is the safety defect.
**Risk:** medium — changes failure timing on a user-facing path.

### Problem (VERIFIED)

Three separate facts compose into an unbounded wait:

1. `HYPERGATE_TIMEOUT_SECONDS = 6.0` at `constants_limits.py:82` is commented
   *"Per-sub-agent call timeout"*. It is not. It is passed as `timeout_seconds`
   into `router.call()`, which forwards it to a single provider attempt.
2. `BaseLLMProvider.__init__` defaults `max_retries=2`, and
   `complete_with_retry` loops `for attempt in range(self.max_retries + 1)` —
   **three** attempts — with `asyncio.sleep(min(2**attempt, 4) + random(0,0.5))`
   between them (`infrastructure/llm/base.py:179-202`). The primary call runs
   with `single_attempt=False`. So one role costs up to `3 x 6s + ~3.5s` of
   backoff before its fallback is even tried.
3. `/api/gate` has **no total ceiling at all**. `api/routes/gate.py:26` awaits
   `decide_route` bare. `PipelineOrchestrator` does have one
   (`orchestrator.py:288-308`, `_guard(..., max(GATE_TIMEOUT_SECONDS*2, 5.0))`),
   so the two entry points into the same gate have different failure semantics.

Measured consequence before `e241bb8`: 30,189 ms on `/api/gate` for one complex
prompt. The only backstop is the 300 s request middleware.

### Design

Two changes, both at the application boundary, mirroring a pattern already in
the codebase.

**(a) A total budget, enforced in `gate_service`.** `decide_route` wraps
`gate.decide()` in `asyncio.wait_for` against a new
`HYPERGATE_TOTAL_BUDGET_SECONDS`. On expiry it returns the same conservative
verdict the orchestrator already produces when its `_guard` fires — action
`pipeline`, low confidence — rather than raising. This is deliberately the
**same** degradation the pipeline path already has, so the two entry points stop
disagreeing.

Pattern: this is the orchestrator's existing `_guard` helper generalised. Prefer
extracting `_guard` into a small shared application-layer utility over writing a
second copy — the duplication of exactly this kind of block is what produced
finding F2. Candidate home: `application/services/gate_service.py` beside
`build_hypergate_router`, or `application/deadlines.py` if a third caller
appears.

**(b) Rename the constant to say what it is.** `HYPERGATE_TIMEOUT_SECONDS` →
`HYPERGATE_ATTEMPT_TIMEOUT_SECONDS`, and correct the comment. Add
`HYPERGATE_TOTAL_BUDGET_SECONDS` next to it. Per **S1**, do the rename in its own
commit with the value unchanged, then add the budget.

**Budget value.** With `ministral-14b` measured at 5.86 s mean *inside the app*
under 5-way concurrency (see W4), a budget below ~8 s would fire routinely on
healthy traffic. A budget above ~15 s does not protect the user. Proposal: **12
s**, revisited after W4 lands, since W4 should cut the contention that makes
5.86 s the mean.

> [INPUT REQUIRED: is a 12 s worst-case gate acceptable as an interim, or should
> the gate degrade to the regex fast-paths sooner and let the pipeline sort it
> out?]

**Retry amplification.** Do **not** change `max_retries` globally in this
workstream — `BaseLLMProvider` is shared by every phase in the system and a
change there is a whole-pipeline behavioural change. If the total budget proves
insufficient, the targeted fix is to construct HyperGate's providers with
`max_retries=0` or to pass `single_attempt=True` for this role, which is a
`build_hypergate_router` concern and stays local. **HYPOTHESIS**: with a model
that answers in <2 s, retries rarely fire and the budget alone is enough.

### Steps

1. Commit A: rename `HYPERGATE_TIMEOUT_SECONDS` →
   `HYPERGATE_ATTEMPT_TIMEOUT_SECONDS` everywhere (`constants_limits.py:82`,
   `base_sub_agent.py:24,39`), value untouched, comment corrected to
   "per provider attempt; a role can cost up to 3x this plus backoff".
2. Commit B: add `HYPERGATE_TOTAL_BUDGET_SECONDS` and enforce it in
   `decide_route`, returning the conservative verdict on expiry.
3. Extract the timeout-guard helper if and only if it removes duplication;
   otherwise inline and note it.
4. Emit a metric on budget expiry so this is observable rather than silent —
   there is already `reasoner_llm_call_failure_total`; add a gate-level counter
   alongside it.

### Tests

- A unit test with a stubbed `HyperGateAgent.decide` that sleeps past the
  budget, asserting `decide_route` returns within budget + epsilon and yields
  the conservative verdict, not an exception.
- A test asserting `/api/gate` and the orchestrator preflight produce the same
  `action` for the same timeout condition. This is the regression that keeps the
  two entry points aligned.
- `tests/test_preflight_gate_isolation.py` already covers the orchestrator side
  and must stay green.

### Verification

```bash
python -m pytest tests/test_preflight_gate_isolation.py tests/test_api_gate.py tests/test_hypergate.py -q
# live: a prompt that reaches full fan-out must return inside the budget
curl -s -X POST localhost:8003/api/gate -H 'content-type: application/json' \
  -d '{"problem":"<complex prompt>","preset":"auto-budget"}' -w '\n%{time_total}s\n'
```

### Rollback

Set `HYPERGATE_TOTAL_BUDGET_SECONDS` very high, or revert commit B. Commit A is
a pure rename and safe to keep.

---

## 5. W4 — Stop the five sub-agents contending on one endpoint

**Priority:** HIGH. This is the remaining latency, and it feeds W3's budget.
**Risk:** medium. Changes which models answer.

### Problem (VERIFIED)

`ministral-14b` answers a single sub-agent prompt in **1.47–1.92 s** when probed
alone. Inside the running app it averages **5.86 s** (`93.83 s / 16 calls`, from
this deployment's own `reasoner_llm_call_duration_seconds`). The five Phase-1
sub-agents fire concurrently via `asyncio.gather` (`hyperagent.py:299-306`) and
all resolve the *same* role, therefore the same provider and the same upstream
endpoint.

**INFERENCE:** the ~3x gap is upstream contention/queueing, not model speed. The
gate's parallelism is currently self-defeating: five concurrent calls to one
endpoint serialise against each other.

### Design

Give each sub-agent its own routing role, so the five can be spread across
vendors, and default them to a small verified pool.

This is the same shape `subagents/base.py` already uses — a per-agent `ROLE`
class attribute — and `e241bb8` already introduced `ROLE` on `BaseSubAgent`. The
change is to override it per subclass instead of sharing one value:

```python
class LanguageDetectorSubAgent(BaseSubAgent):
    ROLE = "hypergate_language"
```

`build_hypergate_router` then populates one entry per role. `ProviderRouter.resolve`
already falls back to `self.primary` for an unmapped role, so a partially
populated table degrades safely rather than raising — **VERIFIED**.

**Which models.** Only from the measured-good set (2026-08-29, five sub-agent
prompts each, verdict = did the reply parse):

| model | parsed | slowest | note |
|---|---|---|---|
| `ministral-14b` | 5/5 | 1.92 s | EU |
| `laguna-s-2.1` | 5/5 | 1.88 s | — |
| `gpt-4o-mini` | 5/5 | 1.81 s | US |
| `grok-4.3` | 5/5 | 4.64 s | US, slow |
| `ministral-3b` | 4/5 | 0.97 s | fails `direct_detector` |
| `laguna-xs-2.1` | 4/5 | 1.20 s | fails `method_classifier` |
| `gemma-4-31b` | 2/5 | — | emits `-1` for string fields |
| `qwen3.6-flash` | 0/5 | — | returns `""` |
| `qwen3.5-flash` | 0/5 | — | returns `-1.0000000000000002e+308` |

The partial models are usable *for the agents they pass*. `ministral-3b` is the
fastest thing measured and fails only `direct_detector`; `laguna-xs-2.1` fails
only `method_classifier`. A per-role table can exploit that, which a single
shared role cannot. **This is the real argument for per-role routing** — not
just contention.

Proposed starting assignment, to be confirmed by measurement:

| role | model | why |
|---|---|---|
| `hypergate_language` | `ministral-3b` | trivial task, fastest verified |
| `hypergate_complexity` | `laguna-xs-2.1` | passes, different vendor |
| `hypergate_direct` | `ministral-14b` | `ministral-3b` fails this one |
| `hypergate_web` | `laguna-s-2.1` | passes, spreads load |
| `hypergate_method` | `ministral-14b` | hardest task, needs the stronger model |
| `hypergate_tiebreak` | `gpt-4o-mini` | hardest task, third vendor |

Fallback for every role: a model from a *different* vendor than its primary, per
the project's cross-lab convention. `_resolve_fallback` only consults
`fallback_table["primary"]` when the failing provider **is** the router primary
(**VERIFIED**, `router.py:377`), so every new role needs its own explicit
fallback entry or it silently inherits the router primary. This is the exact
trap `e241bb8` documented; the test added there
(`test_hypergate_router_gives_the_subagent_role_its_own_fallback`) must be
generalised to loop over all six roles.

**Cost.** Six roles x <=200 output tokens. At the priced tiers involved this is
fractions of a cent per gate call; not a constraint. Confirm against
`domain/pricing.py` rather than assuming.

### Steps

1. Add `ROLE` overrides to the six sub-agent subclasses.
2. Extend `_KNOWN_ROUTING_ROLES` in `domain/preset_core.py` with the six names,
   so presets *may* declare them and `__post_init__` validation accepts them.
   (**VERIFIED**: `hypergate_subagent` is currently absent from that frozenset —
   finding F3 — so any preset declaring it today would raise.)
3. Populate all six in `build_hypergate_router`, each with its own fallback.
4. Generalise the fallback test to all six roles.
5. Re-measure: the same five `/api/gate` probes used throughout, plus the
   per-model histogram, before and after (**S2**).
6. Feed the result back into W3's budget value.

### Tests

- Every `BaseSubAgent` subclass declares a `ROLE` that is in
  `_KNOWN_ROUTING_ROLES` — a parametrised test over the subclass list, so a new
  sub-agent cannot be added without a role.
- Every role in the gate router has an explicit fallback whose model differs
  from both the assigned provider and the router primary.
- No two of the six roles resolve to the same served model unless deliberately
  annotated — the same invariant `validate_presets.py` Invariant C enforces for
  presets, and for the same reason.

### Verification

```bash
python -m pytest tests/test_hypergate.py -q
python scripts/validate_presets.py
# plus the standing five probes, compared against the numbers in §14
```

### Rollback

Point all six roles at `ministral-14b` in `build_hypergate_router`. Behaviour
returns to the `7844682` state without touching the sub-agent classes.

### Open question

> [INPUT REQUIRED: is spreading across three vendors acceptable operationally
> (the assignment table above uses Mistral, Poolside and OpenAI across six
> roles) — three upstream dependencies for one gate decision, four counting a
> cross-vendor fallback for each — or would you rather take the contention and
> keep one vendor? The measured cost of one vendor is ~3x latency; the cost of
> spreading out is that many more ways to have an outage, each of which the
> per-role fallback already covers.]

---

## 6. W5 — Wire the L2 gate cache the architecture already declares

**Priority:** after W4. The cache key depends on W4's routing shape.
**Risk:** medium — a wrong cache key serves one preset's verdict to another.

### Problem (VERIFIED)

- `HyperGateAgent._get_l2_cache` is `return None`; `_set_l2_cache` is `pass`
  (`hyperagent.py:169-175`). `_cache_set` still spawns a fire-and-forget task to
  call the no-op (`:193-197`).
- L1 is `self._cache = {}` created per `HyperGateAgent.__init__`, and a fresh
  `HyperGateAgent` is constructed on **every** request in both `decide_route`
  and the orchestrator preflight. So L1 never survives a request either. The
  same applies to `BaseSubAgent.__new__`'s per-instance `_cache`.
- `gate_service.decide_route`'s docstring claims *"Shares HyperGateAgent's own
  L1/L2 cache, so a following run on the same problem does not re-pay the
  HyperGate LLM cost."* False.
- `docs/adr/003-hypergate-pre-router.md` claims sub-agent results are LRU-cached.
  False.
- `core/ports/shared_cache_port.py`'s own docstring lists *"HyperGate L2 decision
  cache"* as a user of the port. The port exists, `ValkeyCacheAdapter` and
  `InMemoryCacheAdapter` implement it, and the wiring was never done.

So this is not a missing feature. It is a designed-and-unconnected one, with two
documents asserting it works.

### Design

Consume `SharedCachePort` from the application layer. Do **not** reach into a
cache backend from `hypergate/` — that is the arch violation the stub's own
comment says it was avoiding (*"moved to orchestrator layer to avoid arch
violation"*).

Placement: the cache belongs in `gate_service.decide_route`, wrapping the whole
`HyperGateAgent` invocation, not inside `HyperGateAgent`. Reasons:

- `hypergate/` sits below `application/` and should not know about ports it does
  not own.
- Caching the *decision* is what has value; caching individual sub-agent replies
  multiplies key-management cost for a fraction of the benefit.
- It makes the per-request `HyperGateAgent` construction irrelevant instead of
  requiring it to become a singleton, which would be a concurrency hazard.

**The cache key is the safety-critical part.** Today's key is
`sha256(problem)` — problem text only. That is only sound while gate routing is
a global constant. The moment W4 lands, or a preset can influence gate routing,
a bare problem hash serves one configuration's verdict for another. The key must
include a routing identity:

```
gate:v1:{sha256(problem)}:{routing_fingerprint}
```

where `routing_fingerprint` is a stable digest over the six `(role, served
model)` pairs actually in the router — served model, not alias, since aliases
route cross-vendor. There is precedent: the LLM cache bug fixed on 2026-08-26
was exactly a cache key that ignored part of the request (the system prompt).

TTL: `HYPERGATE_CACHE_TTL_SECONDS` already exists at 3600
(`constants_limits.py:84`) and is currently unused. Reuse it.

**What must not be cached.** The existing guard is right and must be preserved:
`decide()` only caches when `confidence >= HYPERGATE_METHOD_THRESHOLD` and the
reasoning does not contain "fallback". A degraded verdict must never be
persisted for an hour.

### Steps

1. Delete `_get_l2_cache` / `_set_l2_cache` / `_safe_create_task` from
   `HyperGateAgent` and the L1 dict, or leave L1 as a genuinely request-scoped
   memo and document it as such. **Prefer deletion** (**S7**) — a per-request L1
   in front of a shared L2 buys nothing, because a single request never asks the
   same question twice.
2. Add a `routing_fingerprint()` to `ProviderRouter`, or compute it in
   `build_hypergate_router` and hand it to `decide_route`. Digest over sorted
   `(role, provider.model)`.
3. In `decide_route`: look up; on miss run the gate; on success store with the
   existing confidence guard and the existing TTL.
4. Inject `SharedCachePort` the same way `ModelRegistryPort` is injected
   (`set_model_registry_port` at `api/__init__.py` / `main.py` / `headless.py`).
   Check whether a setter already exists for the shared cache before adding one.
5. Correct `gate_service`'s docstring and `docs/adr/003` to describe reality.

### Tests

- Same problem twice, same routing → one LLM call, two identical verdicts.
- Same problem, **different** routing fingerprint → two LLM calls. This is the
  test that makes the key correct; it must fail if the fingerprint is dropped.
- A low-confidence / fallback verdict is not stored.
- Cache backend unavailable → gate still answers (degrade, never fail).

### Verification

```bash
python -m pytest tests/test_hypergate.py tests/test_api_gate.py -q
# live: two identical /api/gate calls; the second must be dramatically faster and
# must not increment reasoner_llm_call_duration_seconds_count
```

### Rollback

Feature-flag the lookup (**S4**) — `HYPERGATE_CACHE_ENABLED`, default on, set
false to bypass. Revert is a config change, not a deploy.

---

## 7. W6 — Put vendor lookup behind the registry port; delete `_MODEL_LABS`

**Priority:** after W4 needs it (W4 chooses cross-vendor fallbacks).
**Risk:** medium — this table gates the self-healing loop's mutation acceptance.

### Problem (VERIFIED)

`application/services/harness_guard.py:18` holds `_MODEL_LABS`, a hand-written
map of ~150 model aliases to vendor strings, mirroring the registry. It has
already drifted: `llama-4-scout` had to be hand-added on 2026-08-28, and the
alias rename in `08c6993` produced duplicate keys in it that `ruff` F601 caught.

`get_model_lab` returns `_MODEL_LABS.get(model_alias, "unknown")` (`:124`) and
its docstring says unknown models *"don't count toward diversity"*. **The code
does not do that.** Both invariants use a `set`:

```python
proposed_labs = {get_model_lab(m) for m in proposed_models}
if len(proposed_labs) < EVOLUTION_MIN_CROSS_LAB_DIVERSITY:   # :149
```

`"unknown"` is a set member like any other, so a missing alias **inflates**
`len(proposed_labs)` by one and makes a mutation look more diverse than it is.
And in Invariant 2 (`:157-164`), a fallback whose alias is missing compares as
`"unknown"` and therefore never equals the primary's real lab — so a same-vendor
fallback passes the cross-lab check. Both failure directions are silent, and
both weaken a guard whose entire job is to stop the self-healing loop from
collapsing model diversity.

### Design

Single source of truth, reached through the port (**S6**).

`infrastructure/llm/registry.py` already has `_vendor_of()` — it resolves the
alias to the served model and takes the segment before `/`, so it cannot drift
and it correctly follows cross-vendor aliases. `bloc_of()` sits on top of it.
Neither is exposed on `ModelRegistryPort`, which today offers only
`get_provider` / `contains` / `entry`.

1. Extend `ModelRegistryPort` with `vendor_of(model_id) -> str`,
   `bloc_of(model_id) -> str`, and `resolved_model_of(model_id) -> str`. These
   are pure lookups with no side effects — a natural fit for the existing
   Protocol shape.
2. Implement on `RegistryAdapter` by delegation. No new logic.
3. `harness_guard` consumes the port; `_MODEL_LABS` and `get_model_lab` are
   deleted.
4. Fix the unknown semantics explicitly rather than inheriting them. Pick one
   and write it down:
   - **(a) fail loud** — an alias the registry does not know is a programming
     error in a guard that only ever sees registry aliases; raise.
   - **(b) exclude honestly** — filter unknowns out of the set before `len()`,
     which is what the docstring already promises.

   Recommend **(a)**: `check_mutation_invariants` receives aliases that came
   from routing tables, so an unknown one means the caller is wrong. **(b)** is
   correct if the self-healing loop can propose free-form names.

   > [INPUT REQUIRED: can the evolutionary loop propose a model alias that is
   > not in the registry? If yes, (a) turns a guard rejection into a crash and
   > (b) is the right choice.]

5. Note the semantic difference: `_MODEL_LABS` maps to *vendor* ("mistral",
   "qwen"), while `bloc_of` maps to *geopolitical bloc* (US/CN/EU/OTHER).
   `EVOLUTION_MIN_CROSS_LAB_DIVERSITY` is calibrated against vendor counts. Use
   `vendor_of` for a drop-in replacement; adopting bloc semantics is a separate
   decision with a different threshold (**S1**).

### Tests

- Every alias in `_MODEL_WHITELIST` returns a non-empty vendor through the port.
- A mutation proposing three same-vendor models is rejected — currently passes
  if two of the three are missing from the table.
- A mutation whose fallback is same-vendor-but-unlisted is rejected.
- Port conformance: `RegistryAdapter` satisfies `ModelRegistryPort`
  (`runtime_checkable`, so `isinstance` works as the assertion).

### Verification

```bash
python -m pytest tests/ -q -k "harness or guard or evolution or registry"
python scripts/count_importlinter_exceptions.py    # must stay 60
python scripts/ruff_ratchet.py --max <new>          # deletion lowers it; S8
```

### Rollback

Revert. The port additions are additive and harmless if unused.

---

## 8. W7 — `reasoning.exclude` is a no-op on `qwen3.5-flash`

**Priority:** low, but cheap, and it removes a misleading config.
**Risk:** low.

### Problem (VERIFIED)

`registry.py`'s `qwen3.5-flash` entry carries
`extra_body={"reasoning": {"exclude": True}}`, documented as suppressing the
model's "Thinking Process:" narration. Measured 2026-08-29 with that extra_body
active and `response_format` omitted, the model still opens with:

```
Thinking Process:\n\n1.  **Analyze the Request:**\n    *   Task: ...
```

`extract_json` recovers the object that follows, so nothing is broken — but the
narration is paid for in output tokens on every call, and the config asserts a
control that is not working.

**UNKNOWN:** whether OpenRouter silently ignores `reasoning.exclude` for this
model, whether the parameter name is wrong, or whether the model ignores it. The
registry comment says the OpenRouter catalogue lists `reasoning` /
`include_reasoning` as supported for this served model.

### Steps

1. Probe the OpenRouter API directly for this model with and without the
   parameter and compare token accounting — does `reasoning.exclude` change
   anything measurable at all?
2. If it is a no-op: delete the `extra_body` from the entry and from the
   `qwen3-turbo` alias that copies it, and correct the comment. Keep the
   `response_format` story separate — that is already settled by `7844682`.
3. If the parameter is merely misnamed, fix it and measure the token saving.
4. Either way, quantify: tokens per call x calls per run x the 26 presets
   touching this model, so the follow-up is prioritised on evidence.

### Verification

Compare `reasoner_llm_call_duration_seconds` and OpenRouter usage accounting
before and after on identical prompts.

---

## 9. W8 — Find the 23-violation ruff drift

**Priority:** low. Hygiene, but it hides real regressions.
**Risk:** none.

### Problem (VERIFIED)

`scripts/ci-local.sh` and `.github/workflows/test.yml` carried `--max 2237`.
Measured at `80e36b8` in a clean detached worktree: **2261**. So the lint gate
was failing by 24 before any of this work, because commits landed without moving
MAX in lockstep (**S8**). `7844682` sets it to 2260 with the reasoning recorded
in the workflow comment.

### Steps

1. `git bisect` between the commit that set 2237 and `80e36b8`, running
   `python scripts/ruff_ratchet.py --max 2237` as the test, to find which
   commits moved the count.
2. Decide per commit whether to pay the debt down or record it. The point is not
   to reach 2237 — it is to know what happened, so the ratchet resumes meaning
   something.
3. Consider making the ratchet a pre-push gate rather than CI-only, since the
   whole failure mode is "landed without noticing".

---

## 10. W9 — Documentation and generated artefacts

**Priority:** low, but `VISION_MODELS.md` states a falsehood a reader could act on.
**Risk:** none.

| item | action |
|---|---|
| `VISION_MODELS.md:635` claims `gemini-pro` → `google/gemini-2.5-pro`. It never did; it served `anthropic/claude-sonnet-5` until `08c6993` removed it. | correct or delete the row |
| `docs/preset-phase-model-matrix.md`, `docs/methods_and_presets.md` still use the retired alias names | regenerate, do not hand-edit |
| `docs/DEBATE_FIX_PLAN.md`, `docs/MODEL_REPLACEMENT_GEMINI_FLASH_LITE.md`, `docs/SUGGESTIONS_PLAN.md` use old names | **leave alone** — historical records should keep saying what was true when written |
| `docs/adr/003-hypergate-pre-router.md` claims sub-agent LRU caching works | correct as part of W5, not separately |
| 6 skill maps stale (`ui-next` files from concurrent work) | `python scripts/check_skill_maps.py --update` after reviewing the diff |
| `ARCHITECTURE_MINDMAP.md` / `graphify-out/` go stale because `core.hooksPath` points at `.githooks/`, which has no `post-commit` | either add the hook to `.githooks/` or accept it as manual and say so in one place |

---

## 11. W10 — Development environment

**Priority:** trivial, but it currently blocks `.claude/launch.json`.

Port 8003 is held by PID 9652, which no longer exists as a process
(`Get-Process` fails, `taskkill` reports not found, `netstat` shows it
LISTENING). An orphaned socket. Clears on reboot; until then the backend must
run on another port.

No code change. Worth a line in the dev README if it recurs.

---

## 12. Sequencing

```
W1 (green baseline)
 └─> W2 (delete dead gate agent)
      └─> W3a (rename timeout constant)            ─┐
           └─> W3b (total budget)                   │  W3b's value
      └─> W6 (registry port: vendor_of)             │  depends on W4
           └─> W4 (per-role routing, cross-vendor) ─┘
                └─> W5 (L2 cache, keyed on routing fingerprint)

independent, any time: W7, W8, W9, W10
```

**Why this order.**

- **W1 first** because every subsequent verification is "the suite is green
  except for what I changed", and that is meaningless from a red baseline.
- **W2 before W3** because W3 renames `HYPERGATE_TIMEOUT_SECONDS`, and the dead
  `GateAgent` reads the neighbouring `GATE_TIMEOUT_SECONDS`. Deleting it first
  shrinks the rename's blast radius.
- **W6 before W4** because W4 must choose cross-vendor fallbacks for six roles,
  and doing that against `_MODEL_LABS` would be building on the table W6
  deletes.
- **W4 before W3b** because W4 should cut the 5.86 s contention that otherwise
  forces an uncomfortably large budget.
- **W5 last** because its cache key must fingerprint the routing that W4
  establishes. Landing W5 first would ship a key that W4 invalidates — and a
  stale-verdict bug is worse than no cache.

---

## 13. What this plan does not do

- **Does not touch preset routing.** 26 of 49 presets route to models affected by
  the JSON-mode denylist fixed in `7844682`; whether any of their phases were
  actually degraded depends on `_requests_strict_json` matching their prompts.
  That is a separate investigation with its own measurement, not a fix to bolt
  on here.
- **Does not change `BaseLLMProvider.max_retries`.** Shared by every phase;
  changing it is a whole-system behavioural change (see W3).
- **Does not move `GateDecision`** out of `gate_agent.py`, though it belongs in
  `hypergate/models.py`. Separate commit, touches the public shim.
- **Does not adopt bloc semantics** in `harness_guard`. `vendor_of` is the
  drop-in; switching to blocs changes what the threshold means.
- **Does not revisit the `ministral-14b` choice.** It was measured against eight
  alternatives on the real prompts; revisit when the measurements age, not
  before.

---

## 14. Baseline to measure against

The five standing `/api/gate` probes, as of `7844682`. Any workstream touching
the gate re-runs these and records the result.

| probe | before all work | at `7844682` |
|---|---|---|
| short greeting | 84 ms | 49 ms |
| factual lookup (fast-path) | 1,506 ms | 3,521 ms |
| complex, full fan-out | 30,189 ms | 8,721 ms |
| greek complex | 15,999 ms | 10,462 ms |
| ambiguous / tiebreak | — | 5,441 ms |

Verdict quality matters more than the milliseconds: before, every pipeline
verdict was `confidence 0.0` / `multi_perspective` (the "all sub-agents failed"
hard fallback). At `7844682`: 0.70–0.99 with real methods, 16/16 LLM calls
succeeding, zero fallbacks.

Full suite at `7844682`: **3,927 passed, 3 failed** — the three W1 retires.

---

## 15. Open questions blocking work

1. **W3b** — acceptable worst-case gate latency? 12 s proposed as interim.
2. **W4** — four upstream vendors for one gate decision: acceptable, or keep one
   vendor and accept ~3x latency?
3. **W6** — can the evolutionary loop propose a model alias absent from the
   registry? Determines fail-loud vs filter-honestly.
4. **W1** — is `tests/_data/article_baseline.json` generated or hand-maintained?
   Determines whether step 3 is a regeneration or an edit.
