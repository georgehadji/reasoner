# Defect-hunt V7 — Tier 6: Parsing & State Model

Worktree `.worktrees/defect-hunt`, branch `chore/defect-hunt-t6`, base `23f2321`.
Budget: 8 candidates. Spent: 8. Surface fully triaged.

Surface (the whole list):
`src/reasoner/core/parsing.py` · `src/reasoner/domain/pipeline_state.py` ·
`src/reasoner/domain/preset_core.py` · `src/reasoner/domain/preset_registry.py`

---

## PHASE 1 — Defect-surface map

| Region | File:function | Defect classes present | Reachability | Blast radius | Invariant density |
|---|---|---|---|---|---|
| R1 | `core/parsing.py:extract_json_any` (+ `extract_json`) | 1 (type/serialization), 3 (boundary) | REACHABLE from **every** entry (asgi:app, main.py, headless.ask, api/mcp) via `flows/services.call_llm` → phase parse | **SYSTEM** | invariant (b) — this *is* the invariant |
| R2 | `core/parsing.py:_strip_trailing_commas` / `_sanitize_json_escapes` | 1 | REACHABLE — applied unconditionally on all 5 parse attempts inside R1 | **SYSTEM** | none stated |
| R3 | `core/parsing.py:_repair_truncated_json` / `_extract_balanced_structure` / `_extract_json_dict_fallback` | 1, 3 | REACHABLE (fires on every token-limit cutoff) | **SYSTEM** | none stated |
| R4 | `core/parsing.py:_parse_critique_scores` / `_parse_review_hypotheses` / `_parse_premises` / `parse_evidence_bundle*` | 1, 3 | REACHABLE from Phase 3 / VS-critique / Phase 1 | MODULE→SYSTEM (scores drive top-k) | documented fail-soft: skip malformed entry |
| R5 | `core/parsing.py:_repair_json_quotes` / `_is_structural_quote` | — | **DEAD** (zero call sites in `src/` and `tests/`) | none | — |
| R6 | `domain/pipeline_state.py:PipelineState.__init__` / `__post_init__` / `_ensure_fields_initialized` | 2 (round-trip), 5 (state machine) | REACHABLE via `--resume`, snapshot replay, `_from_dict` | EXTERNALLY-VISIBLE (`--resume`) | invariant (a) — this *is* the invariant |
| R7 | `domain/pipeline_state.py:PipelineField` descriptor + method-state properties | 2, 5 | REACHABLE (every phase read/write) | MODULE | invariant (a) `.get()` convention |
| R8 | `domain/preset_core.py:PipelinePreset.__post_init__` / `_derived_env_vars` | 4 (contract) | REACHABLE at import of `preset_registry` | SYSTEM (import-time raise = total outage) | `_KNOWN_ROUTING_ROLES` closure |
| R9 | `domain/preset_core.py:get_method_from_preset` / `build_auto_preset` / `_METHOD_TO_SLUG` | 4, 5 | REACHABLE via HyperGate auto-preset + `pipeline._get_method_from_preset` | SYSTEM (wrong flow selected) | slug↔method bijection |
| R10 | `domain/preset_registry.py:_REGISTRY` (49 configs) | 4 | Data, loaded at import | SYSTEM | role names, model aliases, bloc diversity |

**Hunt queue** (likelihood × blast_radius × reachability): R2 > R3 > R1 > R6 > R9 > R4 > R10 > R8 > R7 > R5.

Tagged assertions about the map itself:

- **[VF]** `parsing.extract_json` / `extract_json_any` is on the path of every LLM
  response: `grep -rn "extract_json" src/` shows it invoked from `phases/`,
  `subagents/`, `application/flows/`, `hypergate/`. Blast radius SYSTEM confirmed.
- **[VF]** `_repair_json_quotes` and `_is_structural_quote` (R5) have no call site
  anywhere in `src/` or `tests/` — dead code, 40 lines. Not a defect; recorded.
- **[VF]** `_REGISTRY` holds **49** presets, not 48 as `CLAUDE.md` §5 states
  (`multi-perspective-ultra-budget` is the extra, and it is the one preset with no
  `-premium` twin). Documentation drift, not a code defect.
- **[VF]** All 5 `safe_json_loads` call sites in `extract_json_any` pre-process the
  text through `_sanitize_json_escapes(_strip_trailing_commas(...))` — including the
  *first, strict* attempt. There is no path that parses the model's bytes untouched.
- **[VF]** Every method-specific accessor on `PipelineState` goes through
  `MethodState.get()` (`v if isinstance(v, dict) else {}`) or
  `data.setdefault(name, {})`; no direct subscript of a method-state dict exists in
  `domain/`. Invariant (a)'s *coding* rule is honoured in-surface.

---

## PHASE 2 — Suspicion generation

| ID | Suspicion | Class | Violated property (named) | Reach | Severity | Prior | Innocence path |
|---|---|---|---|---|---|---|---|
| D1 | Under a model response whose *string value* contains `,` + whitespace + `}`/`]`, `parsing.py:_strip_trailing_commas` rewrites the value, violating **parse fidelity: `extract_json(json.dumps(x)) == x` for well-formed JSON**, producing a silently altered answer | 1 | Parse fidelity / identity on valid JSON | REACHABLE, every entry | **HIGH** (silently wrong, no error) | high | The rewrite is confined to structural positions, or callers re-validate |
| D2 | Under a model emitting bare `NaN`/`Infinity`, `extract_json` returns non-finite floats, violating **"a parsed score is a finite number in \[0,10\]"**; `safe_float` then clamps NaN to the **upper** bound | 1, 3 | Numeric domain of parsed scores; RFC-8259 serialisability | REACHABLE | **HIGH** | medium | `json.loads` default is documented; downstream guards reject non-finite |
| D3 | Under a token-limit cutoff mid-object where an inner array is complete, `extract_json_any` returns the inner **array**, violating its own stated rule **"always prefer objects over arrays"**, discarding every named key | 1 | Prefer-objects rule / no-silent-field-loss | REACHABLE (truncation is the commonest LLM failure) | **HIGH** | high | The array branch is deliberately first; callers tolerate `{"results": …}` |
| D4 | A `PipelineState` written by an older run fails to load (invariant (a)'s stated reason) | 2 | Invariant (a): older state file must load and run | REACHABLE via `--resume` | CRITICAL if true | medium | Migration in `_from_dict` + `_ensure_fields_initialized` covers it |
| D5 | `PipelineState(core=<dict>, <flat kwarg>)` calls `setattr` on a `dict` → `AttributeError` | 2, 5 | Constructor accepts container-or-flat kwargs | UNKNOWN — no writer produces the mixed shape | MEDIUM | low | `_from_dict` migrates only when the container key is absent |
| D6 | A preset names a routing role outside `_KNOWN_ROUTING_ROLES`, or a model absent from the LLM registry, or has an empty/self-referential fallback, or a duplicate key | 4 | Preset contract closure | Import-time | CRITICAL if true | low | `__post_init__` raises; `tests/test_preset_validation.py` already gates it |
| D7 | `preset_core.get_method_from_preset("coding-budget")` returns `"multi-perspective"`, not the declared `"coding"` → wrong flow strategy | 4, 5 | slug↔method agreement | REACHABLE | HIGH if true | medium | `reasoner/presets.py` shadows it and consults the declared field |
| D8 | The `core_analysis` partial-recovery branch is unreachable when a `[` precedes the first `{`, so a half-broken Phase-2 response degrades further than intended | 1 | Graceful-degradation contract of the partial branch | REACHABLE | LOW | medium | Degrades to *missing*, never to *wrong* |

---

## PHASE 3 — Proof-of-defect

All triggers are pure-string or pure-dict. **No live LLM API calls were made.**
`hypothesis` 6.156.4 is already a project dependency; no dependency was added.

### D1 — trailing-comma repair rewrites string contents

**3a Trigger — FIRED.**

```
payload : {"snippet": "items = [1, 2, ]"}
returned: {'snippet': 'items = [1, 2]'}          # comma silently deleted
payload : {"note": "Choose A, B, or C, } is the closing token."}
returned: {'note': 'Choose A, B, or C} is the closing token.'}   # comma deleted
```

**3b Innocence — NO-DEFENSE-FOUND.** The docstring scopes the function to *trailing*
commas ("before closing braces/brackets"), i.e. syntax. There is no guard, and the
transform runs *before* the first strict `json.loads`, so even a perfectly valid
document is mangled. No caller re-validates against the raw text.

**Verdict: CONFIRMED.** (Severity HIGH: no exception, no log; a coding/PoT answer or
any answer that quotes JSON comes back altered.)

### D2 — non-finite JSON constants survive the parse

**3a Trigger — FIRED.**

```
extract_json('{"logical_consistency": NaN, "feasibility": Infinity}')
  -> {'logical_consistency': nan, 'feasibility': inf}
safe_float(nan) == 10.0        # clamped to the MAXIMUM, not the default
json.dumps(parsed, allow_nan=False) -> ValueError
json.dumps(parsed)             -> '{"logical_consistency": NaN, …}'  # JSON.parse() throws
```

`max(0.0, min(10.0, nan))` returns `10.0` because every comparison with NaN is
false — a missing score reads as a *perfect* score. `_parse_review_hypotheses`
clamps the same way: `max(0.0, min(1.0, nan)) == 1.0`, i.e. certainty.

**3b Innocence — NO-DEFENSE-FOUND** for the parse itself. `json.loads` accepting
`NaN` is a documented CPython default, but nothing downstream rejects non-finite
values, and two independent clamps convert them to the *most favourable* value.

**Verdict: CONFIRMED — NOT FIXED, escalated.** See Phase 5.

### D3 — array fallback pre-empts truncation repair

**3a Trigger — FIRED.**

```
extract_json('{"core_solution": "long text", "critical_insights": ["x","y"], '
             '"action_blueprint": ["do a"], "open_q')
  before: {'results': ['x', 'y']}                       # every key lost
  after : {'core_solution': 'long text',
           'critical_insights': ['x','y'],
           'action_blueprint': ['do a']}
```

**3b Innocence — NO-DEFENSE-FOUND.** The repair block's own comment reads "Try to
repair truncated JSON (token-limit cutoffs) **before falling back**", yet it sits
*after* the array fallback. No caller understands a `results` key — it is produced
only by `extract_json`'s list wrapper.

**Verdict: CONFIRMED.**

### D4 — older state file must still load

**3a Trigger — DID-NOT-FIRE.** 24 executed skew scenarios through the real
`PipelineSerializationService.to_dict` / `_from_dict` / `save` / `load` path (not a
hand-built dict): each of 5 `core` fields dropped, 4 `meta` fields dropped, 4
`cost_state` fields dropped, the top-level `adversarial_*` fields dropped, each of
the 6 whole sub-objects dropped, and the ancient flat format. **All 24 loaded.**
A real file save→load cycle also round-tripped `method_state`, `meta`, `cost_state`.

**3b Innocence — CODE-INNOCENT.** `_from_dict` migrates the flat layout,
`PipelineState.__init__` routes flat kwargs to the right container, `__post_init__`
coerces dict→dataclass, `_ensure_fields_initialized` back-fills defaults, and
`MethodState.get()` returns `{}` for anything non-dict.

**Verdict: CLEARED. Invariant (a) HOLDS [VF].**

Note (not a defect under the documented invariant): the *forward* direction fails —
a state file written by a **newer** build carrying an unknown `core` key raises
`TypeError: PipelineCore.__init__() got an unexpected keyword argument`. The
documented property is old-file→new-reader, which holds.

### D5 — mixed container + flat kwarg

**3a Trigger — FIRED** in isolation: `PipelineState(core={"problem": "A"}, language="French")`
→ `AttributeError: 'dict' object has no attribute 'language'`.

**3b Innocence — CODE-INNOCENT at the reachable level.** `_from_dict` builds the
`core`/`meta`/`remainder` containers only under `if '<key>' not in data`, and pops
the flat keys it migrates, so the mixed shape is never produced by any writer in the
repo. No entry point constructs it.

**Verdict: CLEARED (unreachable).** Recorded as latent.

### D6 — preset contract closure

**3a Trigger — DID-NOT-FIRE.** Table-driven check over all **49** presets:

```
source-level preset keys: 49   duplicates: []
presets with unknown routing/fallback roles: {}
self-referential or empty fallbacks: {}
presets referencing a model absent from infrastructure registry (224 models): 0
build_auto_preset(m, tier) == f"{slug}-{tier}" for all 21 method slugs × 2 tiers: 0 misses
```

**3b Innocence — CODE-INNOCENT.** `PipelinePreset.__post_init__` raises on an unknown
role, and `tests/test_preset_validation.py` already gates roles, aliases and lab
entries over the whole registry.

**Verdict: CLEARED.** No new test added — the existing table-driven test already
covers this exact surface (duplicating it would be noise).

### D7 — method derived from preset name

**3a Trigger — FIRED for the domain function**: `preset_core.get_method_from_preset`
returns `multi-perspective` for `coding-*`, `image-gen-*`, `subagent-*`, and the
display form `cross-language` differs from the canonical `cross_language`.

**3b Innocence — CODE-INNOCENT.** Every production caller imports
`reasoner.presets.get_method_from_preset` (`api/execution/pipeline.py`,
`application/pipeline.py:_get_method_from_preset`), which is a deliberate wrapper:
name patterns lead, and the registry's declared `method` fills in when the patterns
fall through to the default — documented in its docstring. The domain function is
the *derivation half* by design.

**Verdict: CLEARED.**

### D8 — unreachable partial `core_analysis` recovery

**3a Trigger — FIRED (statistical, input-shape dependent).**
`extract_json('blah "core_analysis": "the answer", "key_insights": ["a","b"] blah')`
returns `{"results": ["a","b"]}`: `strip_prose_preamble` cuts at the earliest of
`{`/`[`, so a leading `[` diverts the text into the array path before the partial
branch is consulted.

**3b Innocence — CODE-INNOCENT enough.** The outcome is *missing* data
(`.get("core_analysis")` → `""`, which callers treat as failure), never *wrong*
data. Widening `strip_prose_preamble` would change what the parser accepts across
the whole system for a degenerate input shape.

**Verdict: INDETERMINATE — not fixed, deliberately.** (Tier rule: prefer failing
loudly to guessing at malformed input.)

---

## PHASE 4 — Triage inventory

| Candidate | Trigger | Innocence | Evidence basis | Status |
|---|---|---|---|---|
| D1 string-content corruption | FIRED | NO-DEFENSE-FOUND | **VERIFIED DEFECT** | **CONFIRMED — FIXED** |
| D3 array fallback pre-empts truncation repair | FIRED | NO-DEFENSE-FOUND | **VERIFIED DEFECT** | **CONFIRMED — FIXED** |
| D2 non-finite constants survive parse | FIRED | NO-DEFENSE-FOUND | **VERIFIED DEFECT** | **CONFIRMED — ESCALATED (unfixed)** |
| D8 unreachable partial-recovery branch | FIRED (shape-dependent) | CODE-INNOCENT (degrades to missing) | UNKNOWN | INDETERMINATE |
| D5 mixed container+flat kwarg | FIRED in isolation | CODE-INNOCENT (unreachable) | FALSE (innocent) | CLEARED |
| D4 older state file loads | DID-NOT-FIRE (24 scenarios) | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D6 preset contract closure | DID-NOT-FIRE (49 presets) | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D7 method-from-preset mismatch | FIRED on domain fn | CODE-INNOCENT (shim) | FALSE (innocent) | CLEARED |

Verified defects by severity × reachability × blast radius: **D1 ≈ D3 > D2**.

---

## PHASE 5 — Fix design

### Fix 1 — D1: `_strip_trailing_commas` must skip string literals

```diff
--- a/src/reasoner/core/parsing.py
+++ b/src/reasoner/core/parsing.py
-def _strip_trailing_commas(text: str) -> str:
-    """Remove trailing commas before closing braces/brackets — LLMs emit these often."""
-    # Match comma followed by optional whitespace and a closing brace/bracket
-    return re.sub(r',\s*([}\]])', r'\1', text)
+_TRAILING_COMMA_RE = re.compile(r',\s*([}\]])')
+_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
+
+
+def _strip_trailing_commas(text: str) -> str:
+    """Remove trailing commas before closing braces/brackets — LLMs emit these often.
+
+    Applied ONLY outside string literals. A comma inside a value — ``"items =
+    [1, 2, ]"``, ``"pick A, B, or C, } closes it"`` — is the model's data, not
+    JSON syntax, and rewriting it silently corrupted the answer.
+    """
+    out: list[str] = []
+    pos = 0
+    for m in _JSON_STRING_RE.finditer(text):
+        out.append(_TRAILING_COMMA_RE.sub(r'\1', text[pos:m.start()]))
+        out.append(m.group(0))
+        pos = m.end()
+    out.append(_TRAILING_COMMA_RE.sub(r'\1', text[pos:]))
+    return "".join(out)
```

Scope: 1 function, 15 changed lines (+2 module constants).

**Causal justification.** The verified mechanism is *an unconditional regex over the
whole document*. The fix breaks it by partitioning the text into string literals and
non-string spans and applying the regex only to the latter — a comma inside a string
literally cannot be reached any more. No lower-side-effect fix exists: moving the
strict parse ahead of the repair would only protect *valid* JSON, leaving malformed
JSON (the case the repair exists for) still corrupted.

**Does this widen what the parser accepts?** **No — it narrows nothing and accepts
nothing new.** The only behavioural difference is that certain characters are no
longer *deleted*. The one thing that could newly *fail* is a real trailing comma the
regex now believes lives inside a string literal, which requires an unbalanced
double-quote earlier in the response; the tail after an unterminated final quote is
still treated as non-string, so the common truncation case is unaffected (test
`test_unterminated_final_string_still_repairs_structure`).

**Risk.** Scope: pure function, no I/O, no state. Side effects: none. Regression
risk: LOW — the 36-case malformed-input matrix is byte-identical before and after.
Reversibility: trivial (single-function revert).

### Fix 2 — D3: repair truncated JSON before the array fallback

```diff
--- a/src/reasoner/core/parsing.py
+++ b/src/reasoner/core/parsing.py
+    # Repair truncated JSON (token-limit cutoffs) BEFORE the array fallback.
+    # Ordering is load-bearing: a response cut mid-object still contains whole
+    # inner arrays, so trying arrays first returned that inner array and threw
+    # away every named key of the outer object — the opposite of the
+    # prefer-objects rule above. Repair is a no-op on already-balanced text.
+    repaired = _repair_truncated_json(text)
+    if repaired:
+        try:
+            return safe_json_loads(_sanitize_json_escapes(_strip_trailing_commas(repaired)), max_depth=100)
+        except (json.JSONDecodeError, JSONDepthExceededError):
+            pass
+
     # Fallback to array extraction only if no object found
     if start_arr != -1:
         ...
-
-    # Try to repair truncated JSON (token-limit cutoffs) before falling back
-    repaired = _repair_truncated_json(text)
-    if repaired:
-        try:
-            return safe_json_loads(...)
-        except (json.JSONDecodeError, JSONDepthExceededError):
-            pass
```

Scope: 1 function (`extract_json_any`), pure block move + comment.

**Causal justification.** The verified mechanism is *ordering*: the array branch
matches first on a truncated object and returns before repair is ever attempted. The
fix breaks it by putting repair first. `_repair_truncated_json` returns `None` for
already-balanced text ("already balanced — not a truncation issue"), so genuinely
array-rooted responses still reach the array branch unchanged. No smaller fix exists:
any guard inside the array branch would have to re-derive "is the outer object
truncated?", which is exactly what `_repair_truncated_json` already computes.

**Does this widen what the parser accepts?** **No.** Both branches already existed;
only their order changed. Nothing that previously raised `ParseError` now parses. The
one behavioural change is *which* of two previously-reachable results is returned for
a truncated object containing a complete array — and the new result is the one the
module's own stated rule ("always prefer objects over arrays") demands.

**Risk.** Scope: 1 function. Side effects: none. Regression risk: LOW — root arrays,
empty arrays and truncated arrays all verified unchanged. Reversibility: trivial.

### D2 — `[REQUIRES HUMAN REVIEW: fix chokepoint lies outside the T6 surface]`

The single causal chokepoint is `reasoner/utils/json_safe.py:safe_json_loads`, the
one function all five `extract_json_any` parse attempts funnel through. That file is
**not** in the T6 surface (and is not T7's either), and the coordinator re-scoped T6
to four files mid-run, so the fix is written out but **not applied**:

```diff
--- a/src/reasoner/utils/json_safe.py
+++ b/src/reasoner/utils/json_safe.py
 def safe_json_loads(data: str | bytes, max_depth: int = 100) -> Any:
     """Parse JSON with a strict depth limit.
+
+    Bare ``NaN`` / ``Infinity`` / ``-Infinity`` (a CPython extension, not RFC 8259)
+    become ``None``: a non-finite float clamps to the *upper* bound in every
+    downstream guard, so a missing score would otherwise read as a perfect one.
     """
-    parsed = json.loads(data)
+    parsed = json.loads(data, parse_constant=lambda _c: None)
     _check_depth(parsed, 1, max_depth)
     return parsed
```

Why `None` and not an exception: every consumer in `parsing.py` already normalises
`None` (`float(x.get(k) or 0)`, `safe_float` → `default`), so the value degrades to
*missing* rather than *wrong*, and the result stays RFC-8259 serialisable for SSE.
Raising instead would turn a rare bad value into a hard failure of the whole response.

**Does this widen what the parser accepts?** No — `NaN` was already accepted; it
would now be accepted as `null`. Residual: a bare `NaN` token reaching
`_extract_json_dict_fallback` (only when every structured parse has already failed)
would still become `float("nan")`; that second site needs the same treatment for a
complete fix, which is why this is >1 function and escalated rather than applied.

A `strict=True` xfail test pinning the current wrong behaviour ships with this tier
(`test_non_finite_json_constants_are_rejected`); it will start failing — and must be
un-xfailed — the moment the fix above lands.

### Fix interactions

Fix 1 and Fix 2 both live in `parsing.py` and compose: Fix 2's repair path calls
`_strip_trailing_commas` on the repaired text, so it inherits Fix 1's string safety.
Verified together by the 36-case matrix and the new test file. Neither touches
`domain/`, so the import-linter contract (`domain` has no outer dependencies) is
untouched.

---

## PHASE 6 — Self-review (RAR)

### Fix 1 (`_strip_trailing_commas`)

| Vector | Finding | Tag |
|---|---|---|
| Boundary | `""`, `"   "`, a value that is only `", }"`, a string at index 0, a string at EOF — all covered by executed tests | **FIX HOLDS [VF]** |
| Invalid input | `None` → `TypeError` from `finditer`, same as `re.sub` before (unchanged); wrong type unreachable (callers pass `str`); adversarial: 200 KB input still truncated to 100 KB upstream, `_JSON_STRING_RE` is linear with no nested quantifier → no ReDoS. `test_parsing_fixes.py::TestExtractJsonRedosPrevention` passes | **FIX HOLDS [VF]** |
| State (corrupt / older writer) | Pure function, no state. Older state files never pass through it. Existing `--resume` tests pass | **FIX HOLDS [VF]** |
| Regression | 36-case malformed matrix byte-identical; 5 previously-parsing trailing-comma shapes still parse (`test_structural_trailing_commas_are_still_stripped`); documented behaviour ("remove trailing commas") preserved for syntax positions | **FIX HOLDS [VF]** |
| Concurrency | Pure, no shared mutable state; module-level compiled patterns are immutable and thread-safe | **FIX HOLDS [HYP]** — reasoned only; `re.Pattern` thread-safety is a stdlib guarantee, not something a test here can add |
| New defect | Re-ran classes 1/3 against the changed region: only new failure mode is "unbalanced quote hides a real trailing comma". Covered by `test_unterminated_final_string_still_repairs_structure` (executed) | **FIX HOLDS [VF]** |

### Fix 2 (`extract_json_any` ordering)

| Vector | Finding | Tag |
|---|---|---|
| Boundary | `[]`, `[1,2,3]`, truncated array, truncated object, empty string — all executed | **FIX HOLDS [VF]** |
| Invalid input | `None`/non-str unreachable; adversarial deep nesting still capped by `max_depth=100`; `deep_nest` matrix case unchanged | **FIX HOLDS [VF]** |
| State | Pure function | **FIX HOLDS [VF]** |
| Regression | Root-array, empty-array and truncated-array cases pinned by `test_array_roots_still_reach_the_array_fallback`; `test_bug004_parsing_truncated_json.py` passes unchanged | **FIX HOLDS [VF]** |
| Concurrency | Pure | **FIX HOLDS [HYP]** |
| New defect | A response whose root genuinely *is* a truncated array now goes through repair first — repair reconstructs the same array (`truncated_arr` matrix case unchanged), so no new loss | **FIX HOLDS [VF]** |

No `FIX BREAKS` on any vector; no revision round needed.

---

## PHASE 7 — Tests

New file `tests/test_parsing_string_fidelity.py` (18 tests). Executed, not reasoned.

- Proof-of-defect D1: `test_string_values_survive_trailing_comma_repair` (4 params) —
  fails without Fix 1, passes with it.
- Proof-of-defect D3: `test_truncated_object_keeps_its_keys_not_just_an_inner_array` —
  fails without Fix 2, passes with it.
- Boundary (≥2): `test_empty_and_blank_input_still_yield_empty_dict`,
  `test_string_that_is_only_a_delimiter_sequence`,
  `test_escaped_quote_inside_value_does_not_desynchronise_the_scanner`,
  `test_unterminated_final_string_still_repairs_structure`.
- No-regression (≥1): `test_structural_trailing_commas_are_still_stripped` (5 params),
  `test_array_roots_still_reach_the_array_fallback` (3 params).
- Property: `test_any_valid_json_object_round_trips_unchanged` — `hypothesis`
  (already a project dependency; nothing added), 200 examples, asserts `extract_json`
  is the identity on well-formed JSON objects.
- D2, unfixed: `test_non_finite_json_constants_are_rejected` marked
  `xfail(strict=True)` so it flips to a failure the moment the escalated fix lands;
  `test_safe_float_clamps_nan_to_the_upper_bound_not_the_default` pins the damaging
  consequence.

No new preset test: `tests/test_preset_validation.py` already runs the identical
table over all 49 presets (roles, aliases, lab entries). Adding a second copy would
be duplication, not coverage.

No new `--resume` test: `test_arch_risk_pipeline_state_resilience.py::test_old_format_migration_preserves_all_fields`
and `test_pipeline_state_split.py::test_load_old_format_state_file` already pin
invariant (a); my 24-scenario probe found nothing they miss.

---

## PHASE 8 — Verdict, coverage & residual risk

**Surface audited.** All four in-scope files, all ten regions R1–R10.
`core/parsing.py` at function granularity (every public entry, every private repair
helper); `domain/pipeline_state.py` through an executed 24-scenario save/load skew
matrix; `domain/preset_core.py` + `domain/preset_registry.py` through an executed
table over all 49 preset configs and all 21 method slugs.

**Surface NOT audited.** The *behavioural correctness* of `_repair_truncated_json`'s
"aggressive repair" back-scan (`_last_structural_boundary`) beyond the cases in the
matrix — how much of a long truncated answer it discards is a quality question that
needs real truncated model output, not a unit test. `PipelineField.__set__`'s
interaction with concurrent phase writes (concurrency, needs runtime). The dead
`_repair_json_quotes` / `_is_structural_quote` pair (R5) was not audited for
correctness because it is unreachable. Everything outside the four files.

**Defect classes covered.** 1 (type & serialization) — deep, 12 malformed-payload
families plus a property test. 2 (round-trip / state fidelity) — deep, real
save/load. 3 (boundary & arithmetic) — the in-tier sites (`safe_float`,
`safe_list`, `_parse_*` clamps and slices, empty/singleton collections). 4 (preset
contract) — complete and mechanical. 5 (state machine) — partial: field *ordering*
dependencies inside `PipelineState` were inspected statically only.

**Confirmed, by severity.** 3 HIGH (D1, D3 fixed; D2 escalated). 0 CRITICAL.
**Cleared as innocent: 4** (D4, D5, D6, D7). **Indeterminate: 1** (D8).

**Clean-claim scope.** Regions R6–R10 (`PipelineState` construction and
save/load migration, `PipelinePreset` validation, `build_auto_preset`, the 49
preset configs) were audited for defect classes 2, 4 and 5 and **no VERIFIED defect
was found**. This is not a claim that the state model is sound or that the presets
are correct — only that these regions, under these classes, with these executed
triggers, produced no confirmed defect.

**Residual UNKNOWN set.**
1. Whether `_repair_truncated_json`'s back-scan discards more of a real truncated
   answer than necessary — needs instrumented production output.
2. Whether bare `NaN` actually occurs in this model fleet's output at a rate that
   matters — needs production telemetry; D2's *mechanism* is verified, its *rate* is
   not.
3. Whether the mixed container+flat `PipelineState` kwarg shape (D5) exists in any
   state file written by an intermediate build during the flat→nested migration.
4. Whether `_extract_json_dict_fallback`'s regex key-scan can lift a "key" out of a
   string value and fabricate a field — plausible, not demonstrated.

**Highest-value next hunt.** `application/services/pipeline_service.py`
(`to_dict` / `_from_dict`) — it is the actual serialization engine behind invariant
(a), it is ~350 lines of hand-written per-field reconstruction with ~12 silent
`except: pass` blocks, and it was outside both T6 and every prior tier.

### Uncertainty Acknowledgment

- **Most likely false positive:** D3. The reorder is defensible on the module's own
  stated rule, but if some caller somewhere genuinely relies on receiving
  `{"results": [...]}` from a truncated object, I changed its input. I found no such
  caller (`results` is produced nowhere else), but "found no caller" is weaker than
  "proved none exists".
- **Real defect most likely missed:** something in `_repair_truncated_json`'s
  aggressive back-scan silently truncating a valid long answer at the wrong boundary.
  I tested that it *parses*; I did not test that it *keeps the right amount*.
- **Requires runtime validation:** the frequency of D1's and D2's triggers in real
  model output; whether D1's corruption has been degrading coding/PoT answers in
  production; concurrency behaviour of `PipelineField.__set__`.
- **Static analysis cannot determine:** what fraction of responses arrive truncated;
  whether any deployed state file predates the flat→nested migration; whether the
  49 presets' *model choices* are good (only that the aliases resolve).
- **What would most increase confidence:** a corpus of raw, unparsed LLM response
  strings captured from production (before `extract_json`), replayed through the old
  and new parser to diff the outputs. That single input would settle D1's rate, D2's
  rate, D3's rate, and the residual `_repair_truncated_json` question at once.

---

## Out-of-tier observations (recorded, not edited)

- `src/reasoner/utils/json_safe.py:safe_json_loads` — D2's chokepoint. Diff above.
- `src/reasoner/application/services/pipeline_service.py:~641` — inside the
  `final_solution` reconstruction, the already-a-dataclass branch assigns to
  `data['final_solution']` instead of `core['final_solution']`. Harmless today (the
  branch is unreachable from a JSON load, and `PipelineState.__init__` re-routes the
  key to `core` anyway), but it is a typo waiting to matter.
- `src/reasoner/domain/pipeline_state.py:420` — a stray `self._ensure_fields_initialized()`
  sits *after* `return None` in the `synthesis` property: unreachable. The identical
  line at the end of ~20 method-state setters is reachable but a no-op once
  `_initialized` is set. Cosmetic; not fixed (touching it would move the ruff count
  for no behavioural gain).
- `CLAUDE.md` §5 says 48 presets; the registry holds 49.
