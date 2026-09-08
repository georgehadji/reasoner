# Audit remediation plan

Date: 2026-09-08. Branch at time of writing: `studio-adopt` at `ea93825`.

Source: `docs/plans/implementation_audit_report.md`, the audit of `779586c..HEAD`
against `docs/plans/root-cause-remediation-2026-09-07.md`. That audit found four
blocking items (C-1, C-2, C-3, H-1), four HIGH/MEDIUM, and four LOW. This
document says how to close them without violating the architecture the original
plan was written to restore.

Every number here was measured on the tree above. Claims that were not measured
are labelled HYPOTHESIS.

## The shape of the problem

Three of the four blocking items are the same mistake, not three mistakes:

**A degradation signal was added next to the dangerous value instead of in place
of it.** `spend_limit_service.py` logs a warning and then returns
`SubscriptionTier.FREE`. `_enforce_spend_caps` was fixed inside `_halt_on_cap`
and left silent in the handler that wraps it. Benchmark suites report which
samples failed and then score as if they had not. In each case the *operator*
learns something and the *decision* is unchanged.

P5 asked for "degrade with a signal" as opposed to "swallow". There is a third
state the plan did not name and the implementation walked into: **signal and
proceed on the value you just admitted was wrong.** The remedy is not more
signalling. It is making "could not determine" a value the caller has to handle,
which is the Result-carrying degradation the original plan's own pattern table
already names.

The fourth blocking item (H-1) is why nobody noticed: the ratchet that polices
this cannot see the body shape two of them use.

---

## R1. Fix the ratchet's blind spot first

**Closes:** H-1. **Finds:** C-1 and H-2 automatically, plus 20 more.

### Root cause

`scripts/silent_failure_ratchet.py:57`:

```python
_SWALLOW_RE = re.compile(r"^(pass|return\b.*?)(\s+#.*)?$")
```

Only a handler whose first statement is `pass` or `return ...` is counted. A
handler whose body is `logger.debug(...)` with implicit fall-through returns
`None` just as surely, satisfies none of the contract's three requirements, and
is invisible at any `--max`. Verified: the ratchet lists `executor.py` lines
229, 259, 529 and 812, and not 756 — which is C-1.

### Fix

Replace the line-regex scan with an AST pass, which the script already has the
machinery for (it parses to find multiline strings). A handler counts as a
swallow when all of:

- it catches `Exception` (bare or in a tuple),
- no `raise` anywhere in its body,
- no `degraded(` call in its body,
- and its body is either `pass`/`return ...` (today's rule) **or** consists only
  of logging calls, none at `warning` and above.

The last clause is the new one. `logger.exception(...)` and
`logger.warning(...)` stay uncounted: they leave a trace at a level someone
alerts on, which is the line the contract draws.

### Measured impact

Running that definition over `src/` today finds **22 sites the current script
misses**:

```
api/dependencies.py:686              healing/telemetry_exporter.py:44
application/flows/search_phases.py:58   infrastructure/learning/online_learner.py:96
application/orchestrator.py:274         infrastructure/llm/executor.py:65
application/orchestrator.py:555         infrastructure/llm/executor.py:756   <- C-1
application/orchestrator.py:582         infrastructure/llm/router.py:504
application/pipeline.py:481             infrastructure/llm/router.py:534
application/pipeline.py:658             infrastructure/valkey/cache_adapter.py:43
application/services/api_key_service.py:140   infrastructure/valkey/cache_adapter.py:49
application/services/gate_service.py:229      infrastructure/valkey/state_adapter.py:48
application/services/gate_service.py:239      neuro/cache.py:200
core/degrade.py:78                   <- H-2
```

Count moves 58 → 80. C-1 and H-2 are both in the list, which is the point: the
two defects the audit found by hand are the two the fixed detector finds by
itself.

### Safety

The ratchet is exact-equality in both directions, so raising MAX in the same
commit as the detection change is mandatory, not optional. Nothing else changes
behaviour. Rollback is reverting one file.

### Verification

`python scripts/silent_failure_ratchet.py --max 80` passes on the tree the
change lands on. Adding `except Exception: logger.debug("x")` anywhere under
`src/` turns it red. A unit test in `tests/unit/` asserting the detector
classifies each of the four shapes (pass, return, debug-fallthrough,
warning-fallthrough) the way this section says.

---

## R2. Close the three "signal and proceed" sites

### R2a. The spend guard's own handler — C-1

`infrastructure/llm/executor.py:756`:

```python
        except Exception:
            logger.debug("Spend cap enforcement failed", exc_info=True)
```

`state: PipelineState` is the first parameter of `_enforce_spend_caps` (:720).
Commit `7c586ab` converted the two handlers inside `_halt_on_cap` (:774, :806)
and did not touch the one that wraps them.

**Fix:** `degraded("executor.spend_cap_enforce", None, exc=exc, state=state)`.
One line. It is the same call the same commit used three lines below.

**Test:** `tests/unit/test_spend_cap_enforcement.py:174-187`
(`test_enforcement_failure_never_breaks_a_run`) already makes
`spend_tracker.record` raise. It asserts only `state._spend_cap_exceeded is
False`. Extend it to assert `state.degradations` is non-empty — every sibling
test in that file already does this, and the missing assertion is what let the
defect ship.

**Also:** `7c586ab`'s message claims this was fixed. Correct the record in the
new commit rather than silently superseding it; a reader of `git log` currently
believes a safety-critical path is covered.

### R2b. Benchmarks: attempted is not measured — C-2

Every suite (`suites/coding.py:53` and its seven siblings) returns:

```python
score=valid / total if total > 0 else 0.0,
sample_count=total,     # total = min(calls_per_suite, len(_PROMPTS)) — attempted
```

So a suite whose every judge call raised yields `score=0.0, sample_count=5`.
`engine.py:96`'s guard is `if samples <= 0`, which never fires, and the 0.0 is
persisted through `update_capabilities` into the registry `UtilityScorer` reads.

**Why not simply `sample_count = total - failed`.** `runner.py:124` derives the
benchmark budget from `sample_count`:

```python
calls = result.get("sample_count", 0)
estimated_cost = calls * 0.0005
```

A call that raised may still have cost money — a timeout after tokens were
generated is billed. Redefining `sample_count` as "succeeded" under-counts
spend, which trades a routing bug for a billing bug.

**Fix:** keep `sample_count` meaning attempted, and add the missing dimension.

1. `suites/__init__.py`: `BenchmarkResult` gains `failed_count: int = 0`.
   Additive with a default on a frozen dataclass, so every existing constructor
   still works.
2. Each of the eight suites: pass `failed_count=failed`, and score over what was
   actually measured — `valid / (total - failed)` when `total - failed > 0`,
   else `0.0`. A suite where 2 of 5 calls failed currently reports `valid/5`,
   which understates the model; after this it reports `valid/3`, which is what
   was measured.
3. `runner.run_suite` (:83-88): add `"failed_count": result.failed_count` to the
   success dict, and `"failed_count": 0` to the exception dict, where
   `sample_count` is already 0.
4. `engine.py:95`: `measured = samples - result.get("failed_count", 0)`, and
   guard on `if measured <= 0`. A fully-failed suite then reaches the
   carry-forward path `e637536` already built and tested.
5. `runner.run_all_suites`'s budget line is **left alone**, still reading
   `sample_count`. Spend accounting is unchanged by this change, deliberately.

**Test:** extend `tests/unit/test_benchmarks.py::TestZeroSampleDimensionsAreNotMeasurements`
with a suite whose judge raises on every call but which returns
`sample_count=5, failed_count=5`. Assert the dimension does not appear in
`caps.scores` as a fresh 0.0, and that the previous profile's score is carried
forward. Mutation-check it: with `engine.py` reverted, the new test must fail.

**Also:** `71acaaf`'s message claims the outage no longer scores as a measured
incapability. Correct it.

### R2c. Billing preflight: unknown is not permission — C-3

`spend_limit_service.py` has three lookups whose failure value is also a
legitimate value:

| Function | Fallback | What the caller reads it as |
|---|---|---|
| `pricing_data_available()` :73 | `False` | "prices not loaded" — skips the per-run ceiling at :228 |
| `_preset_routing()` :182 | `{}` | "unknown preset" — `estimate_run_cost` returns 0.0, under every ceiling |
| `_required_tier()` :274 | `SubscriptionTier.FREE` | lowest rank, so the tier refusal at :214 can never fire |

`check_run_allowed` has one call site, `api/execution/pipeline.py:157`, in the
real per-run path before any spend.

**The comment at :271-273 is also wrong and must go.** It cites
`api/dependencies.py::check_preset_access` as "the primary entitlement gate, so
this is the second line, not the only one". That function has **zero production
callers** — grep across `src/` returns only its own definition; the remaining
hits are in `tests/test_bugfixes_regression_round2.py` — and its own body says it
is deliberately not enforced per SEC-017. `_required_tier` is the only tier gate
that runs.

**Fix, split by what kind of decision each one is.** These are not the same
policy and should not get the same treatment:

- **`_required_tier` is an entitlement decision. Fail closed.** Return
  `SubscriptionTier | None`, `None` meaning "could not resolve". `check_run_allowed`
  refuses with a new `SpendRejection(cap_type="preflight_unavailable")` and a
  message telling the caller to retry. Refusing a run costs a user one retry;
  the current behaviour hands every paid preset to every free account for as
  long as the fault lasts.
- **`pricing_data_available` and `_preset_routing` are estimates. Fall back to
  the deployment cap, do not skip the check.** Return `bool | None` and
  `dict | None`. On `None`, `check_run_allowed` applies
  `settings.SPEND_CAP_PER_RUN_USD` instead of the tier's per-run ceiling. This
  is not a new policy: `_enforce_spend_caps` (`executor.py:739-740`) already
  falls back to the deployment-wide `SPEND_CAP_*` settings when state carries no
  tier, so the precedent and the setting both exist.

`False` and `{}` keep their existing, legitimate meanings — genuinely absent
`openrouter_models.json`, genuinely unknown preset — so the tolerated states
stay tolerated and only the *unknown* state changes behaviour.

**Architecture note.** This keeps the policy in `application/services/`, where
`check_run_allowed` already lives, and out of the three helpers, which stay pure
lookups. No new port, no new module. The `degraded()` calls stay exactly where
they are; what changes is the value they return.

**Test:** `tests/unit/test_spend_limits.py` gains one case per helper: make the
import raise, assert (a) the degradation is recorded, and (b) the *decision*
changes — a free-tier caller is refused a premium preset, and the per-run
ceiling applied is the deployment default rather than absent. Assert on the
`SpendRejection`, not on the log; the log is what the current code already does.

---

## R3. Finish the P5 contract

### R3a. Test the metric leg — H-2

`core/degrade.py:75-77` increments the counter inside
`except Exception: logger.debug(...)`, and no test asserts the counter ever
moves (`grep` for `REASONER_DEGRADATION_TOTAL` over `tests/` returns nothing).
A broken import silently disables leg 2 at all 45 sites, evidenced only at
DEBUG — the D11 shape, inside the helper built to prevent it.

**Fix:** two parts.

1. `tests/unit/test_degradation_contract.py` asserts the counter advances across
   a `degraded()` call, reading the child sample for `site="t.site"`.
2. `degrade.py` logs the metric failure at WARNING **once per process**, not
   DEBUG per call — a module-level `_metric_warned` flag. Per-call WARNING would
   be noise; a single one at startup is the difference between "we know metrics
   are down" and D11.

Part 2 also removes `core/degrade.py:78` from R1's list of 22, so land R1 first
and let the count reflect it.

### R3b. Thread state through the preflight degrade — H-4

`orchestrator.py:237` calls
`degraded("orchestrator.spend_cap_preflight", None, exc=exc)` while
`initial_state: PipelineState | None` is a parameter of the enclosing
`preflight()` (:144), already read at :155. First turns pass `None` and lose
nothing; **every follow-up turn** passes a real `PipelineState` which becomes
the run's canonical state (`execute()`: `state = initial_state or PipelineState(...)`).

**Fix:** `state=initial_state`. One line.

**Test:** call `preflight` with a `PipelineState` and a spend-cap lookup that
raises; assert the entry lands in `state.degradations`.

### R3c. Give `degradations` a reader — H-3

The field reaches the SSE `done` payload (`api/execution/pipeline.py:676`) and
stops. Zero references in `ui-next/src`; zero in `main.py`'s console output. The
justification repeated across the P5 commits — "the state field tells the person
reading the answer" — is currently true of no surface a person reads.

**Fix:** mirror what `errors` already does, which is a complete round trip and
therefore the pattern to copy rather than invent:

| Stage | `errors` today | add for `degradations` |
|---|---|---|
| SSE parse | `chat/page.tsx:794,1038` | same handler |
| Store | Zustand `app-store` | same slice |
| Persist | `db.ts:46` | same record |
| Render | `PhaseRenderer.tsx:86` | near the epistemic labels |
| Export | `markdown.ts:1175-1177` ("### Phase errors") | "### Degraded steps" |

Plus `types.ts:28`'s done event gains `degradations?: string[]`.

`main.py`'s console output gets one line when the list is non-empty. HYPOTHESIS:
the CLI is used mostly for `--output` JSON, which already carries the field via
`renderers/_shared.py:343`, so the console line is the smaller half of this item.

**Scope note.** This is `ui-next/` work and the only item here that touches the
frontend. Per the studio rules in `CLAUDE.md` it is a refinement of existing
components, uses no new tokens, and needs no new art direction.

---

## R4. The narrowings and the latent gaps

### R4a. `start_all.py` catches a type it was told covers more than it does — M-1

The comment at :216 claims "urllib.error.URLError and the socket timeouts are
all OSError, so nothing that means 'still starting' escapes." Measured on this
install:

```
issubclass(http.client.HTTPException, OSError)  -> False
IncompleteRead.__mro__ -> (IncompleteRead, HTTPException, Exception, BaseException, object)
issubclass(urllib.error.URLError, OSError)      -> True
```

A server mid-startup returning a partial response raises `IncompleteRead`, which
now escapes and crashes `main()` where it was previously retried. `URLError` is
covered; the `HTTPException` family is not.

**Fix:** `except (OSError, http.client.HTTPException):`, and correct the comment
to name what it actually covers. Blast radius is local dev tooling only.

**Test:** `tests/unit/test_start_all_signals.py` gains a case where the probe
raises `http.client.IncompleteRead(b"")` and the poll keeps going.

### R4b. HyperGate parse failures never set `.error` — M-2

`method_classifier.py:141` and `tie_breaker.py:74` handle the parse failure
inside `_parse_result`, so `SubAgentOutput.error` stays `None` — the field
`hyperagent.py:294` and `:399` already use to tell a failure from a genuine
low-confidence opinion. The `if out.error:` branch at :399 is unreachable for
parse failures.

Routing outcome is unaffected today: confidence is baked to `0.0` in both
fallback dicts, so `_synthesize`'s thresholds land in the same place. This is
latent, not live.

**Fix:** set `error` on the returned `SubAgentOutput` alongside the `degraded()`
call, so the mechanism the codebase already built for this is the one that runs.

**Test:** assert `out.error` is truthy for a malformed reply, and that
`hyperagent`'s :399 branch is reached.

### R4c. Session reads: empty is not unknown — M-3

`neuro/sessions.py:536-572` returns `[]`, which `get_recent_context()` (:433)
feeds into bootstrap context. A corrupt or locked file is indistinguishable from
a session with no history. No `PipelineState` exists at this layer, so only the
operator-side signal is available today.

**Fix:** return `None` for unknown, `[]` for genuinely empty, and have
`get_recent_context()` propagate the distinction to its caller. Same shape as
R2c, one layer down.

### R4d. The LOW items

- **L-1** `api/streaming.py:311-329`: narrowing to `except json.JSONDecodeError`
  left `ev.get("type")` and `collected.append(ev)` outside any handler.
  `sse_utils.py:_event()` always serialises a dict so it cannot fire today.
  Add a one-line comment recording that the protection now rests on the
  serializer's contract; **note the file is at its pinned 337-line cap**
  (`test_layer_boundaries.py::test_streaming_size`), so this needs a line back
  from somewhere.
- **L-2** `event_emission_service.py:131-148`: `except RuntimeError` is right for
  the production bus, but `__init__` takes `bus: Any`, so a plain `Mock()` would
  raise `TypeError` past the "never raises" contract. Type the parameter to the
  `EventBusPort` Protocol rather than widening the catch — the type is the
  actual fix.
- **L-3** `suites/__init__.py:36`: `f"benchmarks.{suite.suite_name}"`.
  Cardinality risk cleared on review (`degrade.py:76` passes only `site` to
  `.labels()`). Remaining issue is grep-ability; cross-reference from
  `degrade.py`'s docstring.
- **L-4** `scripts/run_all_presets.py`: 10 ruff findings, ungated. Leave.
  Whether `scripts/` joins the ratchet's scope is a separate decision.

---

## Sequencing

```
PR 1   R1  ratchet AST detection, MAX 58 -> 80          finds the rest; nothing else changes behaviour
PR 2   R2a executor.py:756 + its test           80 -> 79
       R3a degrade.py metric test + once-per-process    79 -> 78
PR 3   R2b benchmarks failed_count               behaviour change to routing input
PR 4   R2c billing preflight tri-state           behaviour change to who may run what
PR 5   R3b orchestrator state= (one line)
       R4a start_all HTTPException              78 -> 77
PR 6   R3c ui-next degradations round trip       frontend only
PR 7   R4b, R4c, R4d                             latent + LOW
```

R1 first for the same reason P1 came first in the original plan: it makes
everything after it verifiable, and it finds two of the items on this list
without anyone reading code. PR 2 is two one-line source changes plus the two
tests that should have existed.

PR 3 and PR 4 are the risky ones and are deliberately separate. PR 3 changes
what the capability registry receives and therefore what routing sees. PR 4
changes which runs are refused. Neither should ride along with anything else.

## Patterns by module

| Module | Pattern | Why this one |
|---|---|---|
| `scripts/silent_failure_ratchet.py` | AST visitor over a line regex | The rule is about a handler's *body shape*, which is a tree property; the regex could only ever approximate it |
| `application/services/spend_limit_service.py` | Result-carrying degradation, `None` as "unknown" | The plan's own table already names this; the bug is that the fallbacks were in-band values |
| `check_run_allowed` | Policy in one place, lookups stay pure | Fail-closed for entitlement, deployment-default for estimates. No new port, no new module |
| `benchmarks/suites/*` | Add the missing dimension, do not overload the existing one | `sample_count` has a second consumer (budget); redefining it trades a routing bug for a billing bug |
| `core/degrade.py` | Warn-once for the helper's own failure | Per-call WARNING is noise; DEBUG is D11. Once per process is the only level that is both |
| `ui-next/` | Copy the `errors` round trip | It already exists end to end; inventing a second shape for the sibling field is the more expensive option |
| `hypergate/sub_agents/*` | Use `SubAgentOutput.error`, the mechanism already built | `hyperagent.py` already branches on it |

## What this plan does not cover

- Whether `api/dependencies.py::check_preset_access` should be enabled. It is
  dead code with a SEC-017 note saying every tier may reach every preset today.
  That is a product decision. This plan only stops `spend_limit_service.py` from
  citing it as a live backstop.
- The remaining 58 counted swallow sites, and however many of R1's 22 are worth
  converting rather than leaving counted. Same site-by-site treatment the
  original P5 prescribes.
- `runner.py:124`'s flat `$0.0005` per judge call. It is an estimate with no
  bearing on these findings, but it is also not measured against anything.

## Uncertainty

Most likely to be wrong: R2c's fail-closed choice for `_required_tier`. If the
resolution path turns out to fail in normal operation for a reason nobody has
seen yet — an unknown preset id reaching it, say — refusing runs would be worse
than the current over-permissiveness. The test in R2c should therefore assert
the *unknown preset* case still resolves normally and is not swept into the new
refusal. If that distinction proves hard to hold, fall back to applying the
highest tier's ceiling rather than refusing.

Most likely to be missed: another instance of "signal and proceed on the value
you admitted was wrong". R1's AST pass does not detect it — a site can call
`degraded()` correctly and still return a fallback the caller cannot
distinguish. HYPOTHESIS: the detectable subset is "`degraded()` whose fallback
is a falsy literal returned from a function whose caller branches on
truthiness"; worth one exploratory pass before assuming these three were the
only ones.
