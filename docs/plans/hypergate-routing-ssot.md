# HyperGate Routing — SSOT Conformance Plan

Baseline: `studio-adopt` @ `5f64856` (2026-08-29). Every citation below was read against that
tree, with `preset_registry.py` and `scripts/validate_presets.py` in their current
working-tree state.

**Short answer to the question that prompted this plan.** Phase sub-agents
(`src/reasoner/subagents/`) *already* adhere to the SSOT — `execute(state, router)` takes the
active preset's router and calls `role=self.ROLE`
([base.py:71,100](../../src/reasoner/subagents/base.py:71)), and all ten `subagent_*` roles are
registered in `_KNOWN_ROUTING_ROLES` ([preset_core.py:71-81](../../src/reasoner/domain/preset_core.py:71)).
They need no work. **HyperGate is the sole violator**, and it violates in five distinct ways,
two of which are live bugs shipping today.

The plan's end state is *less* code than today, not more: the two duplicated router-override
blocks are deleted outright rather than refactored.

---

## 1. Findings

Severity is "what breaks in production today", not "how ugly is it".

### F1 — HyperGate sub-agents never use the model they are assigned · **CRITICAL, live**

[`base_sub_agent.py:124`](../../src/reasoner/hypergate/base_sub_agent.py:124) resolves the
sub-agent provider:

```python
provider = router.get("hypergate_subagent")
model_name = getattr(provider, "model", "").lower()
is_openai = any(model_name.startswith(p) for p in ("gpt-", "o1", "o3", "openai/"))
```

…then [`:152-153`](../../src/reasoner/hypergate/base_sub_agent.py:152) executes against a
*different* role:

```python
result = await router.call(
    role="primary",
    ...
)
```

`hypergate_subagent` is read once, for a temperature heuristic, and never routed to.

**What the sub-agents actually run on is preset-dependent, and neither answer is the intended
one.** `resolve(role)` returns `routing_table.get(role)` before falling back to `self.primary`
([router.py:349-354](../../src/reasoner/infrastructure/llm/router.py:349)), and `"primary"` is
itself a legal preset routing role ([preset_core.py:23](../../src/reasoner/domain/preset_core.py:23))
that **four presets populate** — `writing-budget`, `writing-premium`, `article-budget`,
`article-premium` ([preset_registry.py:631,647,681,735](../../src/reasoner/domain/preset_registry.py:631)).
Because the override copies the preset's `routing_table`, those four shadow the `grok-4.5`
primary entirely:

| Preset family | `resolve("primary")` returns | So sub-agents run on |
|---|---|---|
| 45 presets with no `routing["primary"]` | `self.primary` | `grok-4.5` — frontier arbiter |
| `writing-*`, `article-*` (4) | `routing_table["primary"]` | that preset's **writing/drafting model** |

Four consequences:

1. **The cheap-classifier design of ADR-003 is defeated.** Six frontier calls per request where
   the intent was five cheap ones plus one arbiter.
2. **Timeouts are near-guaranteed** on a 6s budget
   ([`HYPERGATE_TIMEOUT_SECONDS`](../../src/reasoner/core/constants_limits.py:82)). This is the
   mechanism behind the `confidence: 0.0, "All sub-agents failed or returned very low
   confidence, fallback"` responses observed on 2026-08-28 — reproduced under `auto-budget`,
   which resolves to `multi-perspective-budget` and therefore lands in the 45-preset row.
3. **The gate's model is not deterministic across presets.** A long-form writing model is being
   asked to emit opaque-letter classifications under a 6s budget. Nothing declares this; it is
   an emergent consequence of a role-name collision.
4. **The temperature heuristic reads the wrong model — and is now actively wrong.** `is_openai`
   is computed from `gemini-flash-lite`'s served name, then applied to whichever model the table
   above selects. That was harmless while every candidate was non-OpenAI. It stopped being
   harmless on 2026-08-28: the fallback fix installed `gpt-4o-mini` as
   `fallback_table["primary"]` ([gate_service.py:48](../../src/reasoner/application/services/gate_service.py:48)),
   a genuinely OpenAI model. On any grok-4.5 timeout the gate now falls back to `gpt-4o-mini`
   **carrying `temperature`**, because the sniff inspected a Qwen model and concluded "not
   OpenAI". The comment at [base_sub_agent.py:126](../../src/reasoner/hypergate/base_sub_agent.py:126)
   and [gate_agent.py:153](../../src/reasoner/hypergate/gate_agent.py:153) both state this
   codebase's OpenAI models do not accept `temperature`.

Point 3 is the strongest argument for this plan: the gate's routing is not merely hardcoded, it
is *accidentally* variable in a way no preset author can see or intend. Point 4 is the clearest
demonstration of the cost of that: a one-line fallback fix silently created a second defect
because the model actually being called was not the model the code had inspected.

`gate_agent.py` is *not* affected — it resolves `"primary"` and calls `"primary"`
([:155](../../src/reasoner/hypergate/gate_agent.py:155),
[:170](../../src/reasoner/hypergate/gate_agent.py:170)), internally consistent.

### F2 — The router override is duplicated, and the two copies have diverged · **HIGH, live**

[`orchestrator.py:270-285`](../../src/reasoner/application/orchestrator.py:270) (pipeline
preflight) and [`gate_service.py:36-58`](../../src/reasoner/application/services/gate_service.py:36)
(`/api/gate` HTTP + MCP) are verbatim copy-paste, down to the comment. They are no longer
identical: `gate_service.py` gained
`fallback_table["primary"] = gpt-4o-mini` on 2026-08-28; `orchestrator.py` did not.

So the `/api/gate` path recovers from a grok-4.5 timeout and **the main pipeline path still does
not** — its logs read `retrying with fallback 'N/A'`. Any future fix applied to one copy will
keep missing the other.

### F3 — `hypergate_subagent` cannot be declared by any preset · **HIGH, structural**

The role is injected at runtime
([orchestrator.py:274](../../src/reasoner/application/orchestrator.py:274),
[gate_service.py:39](../../src/reasoner/application/services/gate_service.py:39)) but is absent
from `_KNOWN_ROUTING_ROLES` ([preset_core.py:21-118](../../src/reasoner/domain/preset_core.py:21),
79 roles). `PipelinePreset.__post_init__`
([:279-291](../../src/reasoner/domain/preset_core.py:279)) *raises* on unknown routing keys, so a
preset that tried to declare it would fail at import.

This is the concrete blocker: HyperGate is not merely un-configured, it is **un-configurable**.

### F4 — The gate routers are invisible to ACR · **MEDIUM**

Both blocks call `ProviderRouter(...)` directly instead of
[`from_model_ids`](../../src/reasoner/infrastructure/llm/router.py:786), so `routing_ids` /
`fallback_routing_ids` are empty. The ACR reroute path
([orchestrator.py:169-201](../../src/reasoner/application/orchestrator.py:169)) rebuilds routers
from those ID views and therefore cannot see or re-route HyperGate.

### F5 — HyperGate models escape every preset invariant · **MEDIUM**

Because the models are literals in a function body rather than values in a `routing` dict, they
are skipped by:

| Guard | Location | What is missed |
|---|---|---|
| API-key preflight | [`_derived_env_vars`](../../src/reasoner/domain/preset_core.py:297) | walks `routing.values()` + `fallback_routing.values()`; gate models contribute no required env var |
| Model-exists validation | [`PresetService.build_router`](../../src/reasoner/application/services/preset_service.py:68) | re-checks every routed id against `ModelRegistryPort` |
| Unset-key downgrade | `filter_routing` — [preset_service.py:29-46](../../src/reasoner/application/services/preset_service.py:29) | a gate model whose key is unset is never downgraded to `primary_id` |
| Cross-bloc invariants | [test_preset_bloc_diversity.py](../../tests/unit/test_preset_bloc_diversity.py) | parametrised over `PRESETS[...].get("routing")` |
| Preset validator | [scripts/validate_presets.py](../../scripts/validate_presets.py) | model-value and cross-lab checks |

### F6 — No per-role tuning entries · **LOW**

`hypergate_*` roles appear in none of `PHASE_TEMPERATURES` /
`PHASE_REASONING_EFFORT` ([temperatures.py:30,60](../../src/reasoner/core/temperatures.py:30)) or
`ROLE_TIMEOUTS` ([constants_limits.py:366](../../src/reasoner/core/constants_limits.py:366)).
HyperGate carries its own parallel constants instead (`GATE_TEMPERATURE`,
`HYPERGATE_TIMEOUT_SECONDS`, `HYPERGATE_MAX_TOKENS_*`). Note that every *other* HyperGate
dimension — thresholds, timeouts, token budgets, cache size — is already SSOT'd in
[constants_limits.py:75-92](../../src/reasoner/core/constants_limits.py:75). **Model selection is
the single dimension that was left inline.**

### F7 — All HyperGate caching is dead, and its key ignores routing · **MEDIUM, blocks W4**

Two independent facts, each documented as working:

1. **Every cache is per-instance, and both call sites construct a fresh `HyperGateAgent` per
   request** ([gate_service.py:60](../../src/reasoner/application/services/gate_service.py:60),
   [orchestrator.py:285](../../src/reasoner/application/orchestrator.py:285)), which constructs
   fresh sub-agents at [hyperagent.py:162-167](../../src/reasoner/hypergate/hyperagent.py:162).
   The L1 dicts are therefore always empty on arrival.
2. **L2 is a no-op** — `_get_l2_cache` is `return None`, `_set_l2_cache` is `pass`
   ([hyperagent.py:169-175](../../src/reasoner/hypergate/hyperagent.py:169)).

So the docstring at [gate_service.py:26-28](../../src/reasoner/application/services/gate_service.py:26)
— *"Shares HyperGateAgent's own L1/L2 cache, so a following run on the same problem does not
re-pay the HyperGate LLM cost"* — is false on both halves, and ADR-003's *"Sub-agent results are
LRU-cached to avoid redundant classification"* does not hold in production.

**Why this blocks W4 rather than being a separate cleanup:** the cache key is
`sha256(problem)` / `sha256(f"{AGENT_NAME}:{problem}")`
([hyperagent.py:203](../../src/reasoner/hypergate/hyperagent.py:203),
[base_sub_agent.py:118-119](../../src/reasoner/hypergate/base_sub_agent.py:118)) — **no model,
preset, or routing identity**. That is survivable only while routing is a global constant. The
moment W4 makes gate routing per-preset, a cached verdict from one preset's gate model would be
served for another's. Any revival of this cache must key on resolved routing; see W4.

### F8 — `GateAgent` is dead code with a drifted taxonomy · **LOW, but a trap**

`class GateAgent` ([gate_agent.py:132-242](../../src/reasoner/hypergate/gate_agent.py:132)) is
**never instantiated** in `src/` or `tests/` — only `GateDecision` is imported from the module.
It carries a second `_TAXONOMY` ([gate_agent.py:66-85](../../src/reasoner/hypergate/gate_agent.py:66))
that has drifted from the live one in
[method_classifier.py:26](../../src/reasoner/hypergate/sub_agents/method_classifier.py:26): its
`"F"` is `iterative` where the live map says `jury`, and it lacks `R`/`S`/`T`/`U` entirely.

This matters to this plan for one specific reason: it is the file an SSOT refactor would
naturally edit — it *looks* like the gate's top-level LLM call. Editing it would be a no-op that
reads as a fix. Delete it instead (see W3).

### F9 — Adjacent, out of scope

`presets.build_custom_router` ([presets.py:120-138](../../src/reasoner/presets.py:120)) passes
caller-supplied routing straight to `from_model_ids` without validating against
`_KNOWN_ROUTING_ROLES` — a second SSOT bypass, reached via `PresetService.build_router`'s
`custom_routing` branch. Recorded here so it is not lost; **not** addressed by this plan.

### F10 — HyperGate is not the only model literal in `application/` · **LOW, scope boundary**

Two further hardcoded aliases sit outside the preset SSOT. Neither is caused by HyperGate, and
neither is fixed here — but W2's exit criterion must not be written so loosely that it claims
they are:

| Literal | Location | What it does |
|---|---|---|
| `"claude-sonnet"` | [preset_service.py:63](../../src/reasoner/application/services/preset_service.py:63) | downgrade target for `filter_routing` in the `custom_routing` branch — a custom route whose key is unset silently becomes Claude |
| `"gemini-flash-lite"` | [images.py:143](../../src/reasoner/api/routes/images.py:143) | throwaway router for `ImageModelSelector`; same "cheap classifier" intent as `hypergate_subagent`, same lack of a declaration |

`images.py:143` is the natural second candidate for the pattern this plan establishes, since
`image_generate` is already the precedent being reused (§3). Left for a follow-up.

**A related duplication worth a separate ticket.** `harness_guard._MODEL_LABS`
([harness_guard.py:18-110](../../src/reasoner/application/services/harness_guard.py:18)) is a
~90-line hand-maintained `alias → lab` map mirroring ~150 registry aliases, while the registry
already exports `_vendor_of()` / `bloc_of()`
([registry.py:641-658](../../src/reasoner/infrastructure/llm/registry.py:641)) — which
`router.py:478` imports directly. `get_model_lab()` returns `"unknown"` on a miss and
`check_mutation_invariants` counts `{"unknown"}` as one lab
([harness_guard.py:139-149](../../src/reasoner/application/services/harness_guard.py:139)), so
**drift silently weakens the cross-lab diversity invariant instead of failing loudly**. This is
not hypothetical: a missing `llama-4-scout` entry had to be added by hand on 2026-08-28 when new
routing surfaced it. One confirmed bad entry today: `"gemini-pro": "anthropic"`
([:79](../../src/reasoner/application/services/harness_guard.py:79)) — `gemini-pro` is not a
registry alias at all. (`"gemini-flash-lite": "qwen"` at `:78` looks wrong but is **correct**;
the alias name is the lie, not the map.) Out of scope here; flagged because this plan's W5
invariants should use `bloc_of()`, never `_MODEL_LABS`.

---

## 2. What this plan is bound by

| Constraint | Source | How this plan honours it |
|---|---|---|
| Domain has no outer dependencies | `CLAUDE.md` §1 | New role names and default map live in `domain/preset_core.py`; model *resolution* stays in infrastructure, reached only through `ModelRegistryPort` |
| The one accepted domain→core exception is not widened | [`.importlinter:96-100`](../../.importlinter) | W1 adds no new import to `preset_core.py`; it reuses the `get_model_registry_port()` access already present at [:312](../../src/reasoner/domain/preset_core.py:312) |
| Application → Domain/Core only | `.importlinter` layers | W2 **deletes** application-layer `ProviderRouter(...)` construction rather than adding more; the two `application.orchestrator -> infrastructure.llm.router` / `...preset_service -> ...` ignore entries stay as-is |
| `hypergate/` is a driving pre-router with no application imports | `docs/plans/sycophancy-mitigation.md` §1 | W3 changes one string literal inside `hypergate/`; no new imports |
| Roles are validated at preset construction | [preset_core.py:279-291](../../src/reasoner/domain/preset_core.py:279) | New roles are registered *first* (W1) so nothing can raise at import |
| ADR-004 §5: "each phase role has a configured model; the ProviderRouter resolves roles to models" | [ADR-004](../adr/004-cross-lab-routing.md) | This plan makes HyperGate the last holdout to comply |
| ADR-003: sub-agents are cheap parallel classifiers | [ADR-003](../adr/003-hypergate-pre-router.md) | F1's fix restores the stated design |
| `--resume` on older state files | `CLAUDE.md` §5 | No `PipelineState` field changes; routing is resolved per-run, never serialised into state |
| Cross-bloc fallback convention | ADR-004 §3-4 | Gate primary and its fallback are drawn from different blocs; asserted by W5 |

---

## 3. Patterns reused (not invented)

| Need | Existing pattern | Reference |
|---|---|---|
| A role in the SSOT that is *resolved* by non-preset machinery | `image_generate` — registered in `_KNOWN_ROUTING_ROLES`, excluded from ACR with a justifying docstring | [preset_core.py:115](../../src/reasoner/domain/preset_core.py:115) + [`ACR_EXCLUDED_ROLES`](../../src/reasoner/application/services/role_requirements.py:379) |
| Data-driven role definition with a default list | `DEFAULT_PERSPECTIVES` + `routing_key` + the 4-step add-contract in the module docstring | [perspectives.py:5-11,35](../../src/reasoner/core/perspectives.py:5) |
| Role-keyed config table in `core/` | `ROLE_TIMEOUTS`, `PHASE_TEMPERATURES` | [constants_limits.py:366](../../src/reasoner/core/constants_limits.py:366), [temperatures.py:30](../../src/reasoner/core/temperatures.py:30) |
| Preset-declared cross-bloc fallback | `fallback_routing` dicts added to the article presets, 2026-08-28 | [preset_registry.py:713,758](../../src/reasoner/domain/preset_registry.py:713) |
| Invariant asserted across all presets | parametrised bloc-diversity tests | [test_preset_bloc_diversity.py](../../tests/unit/test_preset_bloc_diversity.py) |
| Classification-shaped tuning values | `classification: 0.3 / "minimal"` | [temperatures.py:31,61](../../src/reasoner/core/temperatures.py:31) |

`image_generate` is the closest precedent and should be read before implementing W1: it is
exactly the case of "a role that must live in the SSOT for validation and key-preflight, but
whose selection logic lives in `hypergate/`".

---

## 4. The design decision

### 4.1 The circularity objection, and why it does not hold

The obvious objection to putting HyperGate in the preset SSOT: *HyperGate chooses the method,
and the method chooses the preset — so there is no preset to read routing from.*

This is false in the current code. `gate_service.py:30-34` already resolves a concrete preset
**before** invoking the gate:

```python
raw_preset = preset or "auto-budget"
gate_preset_name, is_auto, auto_tier = preset_service.resolve(raw_preset)
tier = auto_tier if is_auto else get_preset_price_tier(gate_preset_name)
_effective_preset_name, router_instance = preset_service.build_router(gate_preset_name)
```

The **tier** (budget/premium) is user-supplied and known up front; only the **method** is
unknown. `build_auto_preset(method, tier)`
([preset_core.py:223](../../src/reasoner/domain/preset_core.py:223)) resolves the tier-default
preset without knowing the method. A router therefore always exists when HyperGate runs — the
existing code proves it, because it takes that router and mutates a copy of it.

Preset-scoped HyperGate routing is not circular. It is what the code is already reaching for.

### 4.2 Chosen approach: two new roles on the *existing* router

Rather than building a second `ProviderRouter` with a shadowed primary, register two roles and
let HyperGate call them on the preset's own router:

- `hypergate_primary` — the TieBreaker / top-level gate decision
- `hypergate_subagent` — the five parallel classifiers

Defaults merge in at preset construction, so **every** preset router carries them and neither
caller needs special-case code.

This is strictly smaller than the status quo. It deletes:

- both `ProviderRouter(...)` construction blocks (F2)
- the `primary=grok-4.5` shadow, which currently overwrites the preset's real primary for the
  whole gate router
- **the `"primary"` role-name collision** — the direct cause of F1's non-determinism. Once the
  gate calls `hypergate_primary`, a preset declaring `routing["primary"]` for its own drafting
  model can no longer silently capture the gate.
- the `from_model_ids` bypass, restoring ACR visibility (F4)
- the possibility of the two paths diverging again

and it gains per-preset overridability for free — a budget preset can route the gate to a cheap
model, premium to a stronger one, using the ordinary `routing` dict.

### 4.3 Rejected alternatives

| Option | Why rejected |
|---|---|
| Named constants in `core/`, still applied via a router override | Fixes readability only. Leaves F2 (duplication), F4 (ACR blindness), F5 (invariant escape) untouched, and remains un-overridable per preset. |
| Explicit `hypergate_*` entries in all 49 presets | Maximally greppable but 98 lines of near-identical config; a new preset silently omits them. Defaults + opt-in override gives the same explicitness where it matters. |
| Leave HyperGate outside the SSOT, document as deliberate | Defensible for a *pre-preset* component — but F1/F2 are live bugs regardless, and §4.1 shows the pre-preset premise is false. |

---

## 5. Architecture placement map

```
                                   ┌──────────────────────────────────────────┐
 W1  role registration ────────────▶ domain/preset_core.py                    │
                                   │   _KNOWN_ROUTING_ROLES     +2 roles      │
                                   │   DEFAULT_HYPERGATE_ROUTING   (new)      │
                                   │   __post_init__            merge defaults│
                                   │ application/services/                    │
                                   │   role_requirements.py  ACR_EXCLUDED +2  │
                                   │ core/temperatures.py    +2 temp/effort   │
                                   │ core/constants_limits.py  ROLE_TIMEOUTS  │
                                   └──────────────────────────────────────────┘
                                   ┌──────────────────────────────────────────┐
 W2  delete the overrides ─────────▶ application/orchestrator.py     −16 lines│
                                   │ application/services/gate_service.py     │
                                   │                                 −22 lines│
                                   └──────────────────────────────────────────┘
                                   ┌──────────────────────────────────────────┐
 W3  sub-agent role fix ───────────▶ hypergate/base_sub_agent.py    role= str │
                                   │ hypergate/gate_agent.py        role= str │
                                   └──────────────────────────────────────────┘
                                   ┌──────────────────────────────────────────┐
 W4  per-preset overrides ─────────▶ domain/preset_registry.py   opt-in only  │
                                   └──────────────────────────────────────────┘
                                   ┌──────────────────────────────────────────┐
 W5  invariants ───────────────────▶ tests/unit/test_hypergate_routing_ssot.py│
                                   │ tests/unit/test_preset_bloc_diversity.py │
                                   │ scripts/validate_presets.py              │
                                   └──────────────────────────────────────────┘
                                   ┌──────────────────────────────────────────┐
 W6  docs ─────────────────────────▶ docs/adr/003-hypergate-pre-router.md     │
                                   │ CLAUDE.md §5 invariants                  │
                                   │ .claude/skills/map-hypergate/SKILL.md    │
                                   └──────────────────────────────────────────┘
```

No arrow crosses a layer boundary inward. `hypergate/` gains no imports; `domain/` gains no
dependency it did not already have.

---

## 6. Workstreams

### W1 — Register the roles · *prerequisite for everything else*

**W1.1** Add to `_KNOWN_ROUTING_ROLES` ([preset_core.py:116](../../src/reasoner/domain/preset_core.py:116),
alongside the existing trailing groups):

```python
    # HyperGate pre-router (see ADR-003). Resolved on the preset's own router;
    # selection logic lives in hypergate/, like image_generate.
    "hypergate_primary",
    "hypergate_subagent",
```

**W1.2** Declare defaults in `preset_core.py`, near `_METHOD_TO_SLUG`:

```python
DEFAULT_HYPERGATE_ROUTING: dict[str, str] = {
    # Arbiter: one call, needs judgment. Cross-bloc from the sub-agent tier.
    "hypergate_primary": "<arbiter-model>",
    # Five parallel classifiers on a 6s budget — must be fast and cheap.
    "hypergate_subagent": "<classifier-model>",
}

DEFAULT_HYPERGATE_FALLBACK: dict[str, str] = {
    "hypergate_primary": "<cross-bloc arbiter fallback>",
    "hypergate_subagent": "<cross-bloc classifier fallback>",
}
```

Concrete model choice is deliberately left open — see §9 Open questions. The *shape* is what
this workstream fixes.

**W1.3** Merge defaults in `__post_init__`, **before** the existing role validation at
[:279](../../src/reasoner/domain/preset_core.py:279):

```python
self.routing = {**DEFAULT_HYPERGATE_ROUTING, **self.routing}
self.fallback_routing = {**DEFAULT_HYPERGATE_FALLBACK, **self.fallback_routing}
```

Preset-declared values win. Note this rebinds to a **new dict** rather than mutating in place,
which also closes the aliasing hazard flagged during research: `get_preset` documents itself as
returning "a copy" ([preset_registry.py:1025](../../src/reasoner/domain/preset_registry.py:1025))
but passes the registry's `routing` object by reference, and `__post_init__` currently mutates
`required_env_vars` in place on the module-level `_REGISTRY`.

**W1.4** Secondary tables — each must be updated or a CI gate fails:

| Table | File | Value | Why |
|---|---|---|---|
| `ACR_EXCLUDED_ROLES` | [role_requirements.py:379](../../src/reasoner/application/services/role_requirements.py:379) | add both roles + docstring | `test_acr_coverage.py:149-157` requires every role to resolve to an ACR requirement; utility-scoring a latency-bound classifier would pick an expensive model, exactly the F1 failure. Mirrors the `image_generate` rationale. |
| `PHASE_TEMPERATURES` | [temperatures.py:30](../../src/reasoner/core/temperatures.py:30) | `0.3` both | Matches `classification: 0.3`. |
| `PHASE_REASONING_EFFORT` | [temperatures.py:60](../../src/reasoner/core/temperatures.py:60) | `"minimal"` both | Matches `classification: "minimal"` — "fast routing, no deep thought needed". |
| `ROLE_TIMEOUTS` | [constants_limits.py:366](../../src/reasoner/core/constants_limits.py:366) | see note | HyperGate passes `timeout_seconds` explicitly today; add entries only if W2 stops passing the override. Decide during implementation, do not add speculatively. |

*Exit:* `python -c "import reasoner.presets"` succeeds (all 49 presets construct);
`pytest tests/test_preset_validation.py tests/unit/test_acr_coverage.py` green.

### W2 — Delete both router-override blocks

Replace [gate_service.py:36-58](../../src/reasoner/application/services/gate_service.py:36) and
[orchestrator.py:270-285](../../src/reasoner/application/orchestrator.py:270) with direct use of
the router that already exists in each scope:

```python
gate = HyperGateAgent(router_instance)   # gate_service.py
gate = HyperGateAgent(router)            # orchestrator.py
```

Every override the blocks performed is now supplied by W1's defaults. This resolves F2 (one code
path, cannot diverge), F4 (`from_model_ids` view preserved), and F5 (models flow through
`PresetService.build_router`'s validation, `filter_routing`, and `_derived_env_vars`).

Drops the `preset_id=f"hypergate-{...}"` telemetry tag. If that tag is load-bearing for
cost attribution, preserve it via the existing per-call telemetry rather than by rebuilding a
router — confirm against `_emit_telemetry`
([router.py:417](../../src/reasoner/infrastructure/llm/router.py:417)) before deleting.

**Import-contract note.** `application.services.gate_service` imports
`infrastructure.llm.router` at [:17](../../src/reasoner/application/services/gate_service.py:17)
but has **no** `ignore_imports` entry of its own — it passes today only because grimp resolves
it through the already-ignored `application.services.preset_service -> ...router` chain. W2
*removes* that import rather than adding one, so it can only improve the contract. Do not
substitute a new infrastructure import here without adding an `.importlinter` line; consuming
`ModelRegistryPort` instead needs none, since `core` sits below `application`.

*Exit:* `grep -rn "grok-4.5\|gemini-flash-lite" src/reasoner/application/` returns nothing.
Note this deliberately does **not** assert "no model literals in `application/`" — F10's
`"claude-sonnet"` in `preset_service.py:63` is out of scope and would fail such a check.

### W3 — Fix the sub-agent role mismatch · *the live bug*

**W3.1 — adopt the `ROLE` class-attribute pattern.** HyperGate sub-agents declare no `ROLE`;
the role is hardcoded as the literal `"primary"` in the shared base. That is the structural
difference from phase sub-agents, where `ROLE` is a class attribute each subclass overrides and
passes straight through ([subagents/base.py:37,100](../../src/reasoner/subagents/base.py:37)).
Mirror it rather than substituting a different literal:

```python
# hypergate/base_sub_agent.py
ROLE: str = "hypergate_subagent"     # class attribute, overridable per sub-agent
```

then at [:124](../../src/reasoner/hypergate/base_sub_agent.py:124) and
[:153](../../src/reasoner/hypergate/base_sub_agent.py:153) use `self.ROLE` in **both** places —
one role, resolved and called. This is what makes the `is_openai` sniff finally inspect the
provider it is about to call, closing F1 point 4.

`TieBreakerSubAgent` ([tie_breaker.py:45](../../src/reasoner/hypergate/sub_agents/tie_breaker.py:45))
is the one that may warrant `ROLE = "hypergate_primary"` — it is the arbiter, runs once, and is
the call the `hypergate_primary` role was conceived for. Confirm during implementation; the
class-attribute shape makes it a one-line decision either way.

**W3.2 — delete `class GateAgent`** ([gate_agent.py:132-242](../../src/reasoner/hypergate/gate_agent.py:132))
rather than editing it. Per F8 it is unreachable and its `_TAXONOMY` has drifted from the live
one, so "fixing" its role strings would be a no-op that looks like a fix and would leave the
drifted taxonomy in place as a trap for the next reader. Preserve `GateDecision` and
`_GATE_SYSTEM_PROMPT` if anything still imports them — `hyperagent.py:26` and
`hypergate/__init__.py:1` import only `GateDecision`.

Safe because `ProviderRouter.resolve` falls back to `self.primary` for an unknown role
([router.py:349-354](../../src/reasoner/infrastructure/llm/router.py:349)) — so even if W1's
defaults were somehow absent, behaviour degrades to today's rather than raising.

*Exit:* a gate run logs sub-agent calls against the classifier model, not the arbiter model;
`grep -rn "GateAgent" src/` returns only `HyperGateAgent`.

### W4 — Per-preset overrides · *opt-in, not required*

With W1-W3 landed, any preset may override by adding the roles to its ordinary dicts:

```python
"routing": {
    "hypergate_subagent": "<cheaper-or-stronger>",
},
```

Do **not** bulk-add to all 49 presets. Add only where a tier genuinely warrants a different gate
— most plausibly premium presets buying a stronger arbiter. Each override should carry the
one-line bloc/price comment the surrounding entries use.

**Precondition — the cache key.** Per F7 the HyperGate cache keys on the problem string alone.
It is inert today (fresh agent per request), so this is latent rather than live. But W4 is the
change that makes it dangerous: as soon as two presets can resolve different gate models, a
verdict cached under one must not be served for the other. Before landing any override, either
(a) include the resolved gate model ids in `_cache_key`
([base_sub_agent.py:118](../../src/reasoner/hypergate/base_sub_agent.py:118)) and
[hyperagent.py:203](../../src/reasoner/hypergate/hyperagent.py:203), or (b) confirm the cache is
still per-request-instance and record that W4 depends on it staying that way. (a) is preferable:
it makes reviving the cache safe instead of leaving a tripwire.

### W5 — Invariants

New `tests/unit/test_hypergate_routing_ssot.py`:

1. Both roles are in `_KNOWN_ROUTING_ROLES`.
2. Every preset in `PRESETS`, once constructed, resolves both roles to a registry-known model.
3. `hypergate_primary` and `hypergate_subagent` are cross-bloc from each other — reuses
   `bloc_of()` exactly as [test_preset_bloc_diversity.py:175](../../tests/unit/test_preset_bloc_diversity.py:175) does.
4. Each role's fallback is cross-bloc from that role's primary — the invariant whose absence
   caused the 2026-08-28 `fallback 'N/A'` incident.
5. **Regression guard for F1:** assert `base_sub_agent` calls the role it resolved. Cheapest
   durable form is a fake router recording `(resolved_role, called_role)` and asserting equality
   — a string-literal grep would rot.
6. **Regression guard for the role collision.** Build a router from `article-budget` (one of the
   four presets that declares `routing["primary"]`) and assert the gate resolves its own
   `hypergate_primary`, *not* that preset's drafting model. This is the case that silently
   misroutes today; without it, a future re-collision is invisible.
7. No literal model alias appears in `application/services/gate_service.py` or
   `application/orchestrator.py`.
8. **Temperature-sniff correctness (F1 point 4).** Route the gate to an OpenAI-family model and
   assert the outgoing call carries no `temperature`. Today this fails on the fallback path —
   `gpt-4o-mini` receives `temperature` because the sniff read a Qwen model. This test is what
   stops the sniff and the call from drifting apart again.

Extend `scripts/validate_presets.py` to cover the two roles in its cross-bloc pass.

### W6 — Documentation

- **ADR-003** — add a "Routing" section: the two roles, that they resolve on the preset router,
  and that sub-agents are cheap by design (making F1's regression visible as a doc violation).
  Also correct its *"Sub-agent results are LRU-cached to avoid redundant classification"* —
  per F7 that has never held in production. Either implement it or stop claiming it; a
  consequence listed as "Positive" that does not occur is worse than an absent one.
- **`gate_service.py:26-28` docstring** — delete or correct the "Shares HyperGateAgent's own
  L1/L2 cache" claim (F7). It is copied verbatim into
  [api/routes/gate.py:5](../../src/reasoner/api/routes/gate.py:5), so fix both.
- **CLAUDE.md §5 Key Invariants** — one line: HyperGate routing is preset-declared like any other
  role; no model literals in `application/`.
- **`map-hypergate` skill** — record the two roles so the next reader finds them without tracing
  `router.get`.
- Consider a short `docs/adr/` note if W4 ever diverges gate routing per tier.

Two documentation drifts surfaced during research. Both are pre-existing and unrelated to
HyperGate; fix opportunistically while editing these files, or spin off:

- `CLAUDE.md` and [ADR-004](../adr/004-cross-lab-routing.md) both state **"28 directly registered
  models"**. `_MODEL_WHITELIST` ([registry.py:29-499](../../src/reasoner/infrastructure/llm/registry.py:29))
  holds **226** aliases.
- `CLAUDE.md` §3 states **48 presets**; `_REGISTRY` holds **49**
  (`multi-perspective-ultra-budget` at [preset_registry.py:44](../../src/reasoner/domain/preset_registry.py:44)
  is the extra).

---

## 7. Sequencing

W1 → W2 → W3 must be ordered: W1 makes the roles declarable, W2 makes the preset router the only
router, W3 points HyperGate at the roles. W3 before W2 would route sub-agents to a role the
override blocks do populate — correct, but it would mask whether W2 actually worked.

W5 lands with W3 (the regression guard is the point). W4 and W6 are independent tails.

A defensible smaller first PR is **W1 + W3 only**: that fixes the live F1 bug and makes the roles
real, while leaving the duplicated blocks in place for a follow-up. W2 is the larger blast radius
and benefits from landing alone.

---

## 8. Verification

| Check | Command |
|---|---|
| All 49 presets still construct | `python -c "import reasoner.presets"` |
| Preset + ACR gates | `pytest tests/test_preset_validation.py tests/unit/test_acr_coverage.py -v` |
| Bloc diversity + new SSOT invariants | `pytest tests/unit/test_preset_bloc_diversity.py tests/unit/test_hypergate_routing_ssot.py -v` |
| HyperGate behaviour | `pytest tests/test_hypergate.py tests/test_api_gate.py -v` |
| Layer contract | `lint-imports` (run via PowerShell — the rtk shim suppresses lint stdout) |
| Preset validator | `python scripts/validate_presets.py` |

**Live check that F1 is actually fixed.** Before: five sub-agent calls against the arbiter model,
6s timeouts, `confidence: 0.0`. After: sub-agent calls against the classifier model, sub-second,
non-zero confidence. Observe via `preview_logs` on the backend during a real `/api/gate` POST —
this is the observation that originally exposed the bug and is the one that should confirm it.

---

## 9. Open questions — resolve before implementing W1.2

1. **Which arbiter model?** `grok-4.5` is the incumbent but is a poor fit for a 6s budget. Its
   selection appears undocumented — no ADR or comment justifies it. Either justify it and raise
   `HYPERGATE_TIMEOUT_SECONDS`, or pick a faster arbiter. **`[INPUT REQUIRED: is grok-4.5 a
   deliberate quality choice for the gate arbiter, or an unreviewed default?]`**
2. **Which classifier model?** `gemini-flash-lite` is the stated intent — note it is a
   cross-vendor alias to a Qwen model, not Google
   ([harness_guard.py:39](../../src/reasoner/application/services/harness_guard.py:39)); the name
   misleads and any cross-bloc assertion must use `bloc_of()`, never the alias string.
3. **Does the `hypergate-` telemetry prefix matter?** Determines whether W2 can delete cleanly
   (see W2 note).
4. **Should the gate honour ACR at all?** This plan excludes it, matching `image_generate`. If
   HyperGate should instead adapt its models to observed latency, that is a different and larger
   design — out of scope here, but the exclusion is the decision point.

---

## 10. Non-goals

- `presets.build_custom_router` role validation (F9).
- Redis/Valkey availability. The `Redis circuit breaker unavailable` warnings that accompany
  every gate call are a separate local-environment gap; every call site fails open and none of
  them cause F1-F8.
- Changing HyperGate's classification logic, prompts, opaque-letter scheme, thresholds, or cache.
  This plan moves *where models are declared*, nothing else.
- The `harden_system_prompt()` exclusion for HyperGate sub-agents, which is deliberate and
  documented at [base_sub_agent.py:143-151](../../src/reasoner/hypergate/base_sub_agent.py:143).
