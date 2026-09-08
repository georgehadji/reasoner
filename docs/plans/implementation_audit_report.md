# Implementation audit: P2 and P5 of the root-cause remediation plan

Date: 2026-09-08.
Reviewed range: `779586c..HEAD` (`ea93825`), branch `studio-adopt`. 21 commits,
89 files, +3871 / -720.
Plan under review: `docs/plans/root-cause-remediation-2026-09-07.md`.
Architecture reference: `CLAUDE.md` sections 1, 5, 7; `.importlinter`;
`tests/architecture/`.

Disclosure, and a finding in its own right: the author of the reviewed commits
produced the first pass of this report, and that pass **missed three CRITICAL
defects**, all of which an independent adversarial review then found. Every one
was re-verified here by running something. Self-review of one's own change
under-detects; the corrected findings below are the evidence. Conclusions that
could not be established by running a command are labelled HYPOTHESIS.

---

## 1. Executive summary

The range implements P2 in full and P5 steps 1, 2 and 5. **P5 step 4 is Partial,
not Complete**, and two commit messages claim fixes that did not land.

What is genuinely good: `core/degrade.py::degraded()` has the signature the plan
specifies, 45 sites route through it, the four exception trees are merged, the
router catches `ProviderError`, the second `BaseLLMProvider` is gone, and the
tests are not vacuous under mutation.

What is wrong, in severity order:

- **`7c586ab` did not fix the thing its title claims.** "A spend guard that has
  stopped guarding now says so" converted two handlers *inside* `_halt_on_cap`
  and left `_enforce_spend_caps`'s own outer handler at
  `executor.py:756` as `except Exception: logger.debug(...)` — with
  `state: PipelineState` sitting in the signature. A failure anywhere in the
  enforcement body disables the spend cap for that call, silently.
- **`71acaaf` did not fix the thing its title claims.** "An outage no longer
  scores as a measured incapability" added a warning; the outage still scores as
  a measured incapability. Suites set `sample_count=total` where `total` is
  *attempted*, so a suite whose every judge call raised reports `score=0.0` with
  a non-zero sample count, sails past `engine.py:96`'s `if samples <= 0` guard,
  and is written into the capability registry that routing reads.
- **Three billing fallbacks in `spend_limit_service.py` signal and then proceed
  on the dangerous value**, one of them citing a "second line of defence"
  (`api/dependencies.py::check_preset_access`) that has zero production callers.
- **The ratchet cannot see the shape of swallow that `executor.py:756` is.**
  `_SWALLOW_RE` matches only `pass` and `return ...`; a
  `logger.debug(...)`-and-fall-through body is invisible to it at any `--max`.
  So "58 remaining sites" means "58 of two specific body shapes", not 58 bare
  swallows.
- The metric leg of the three-part contract is untested, and `degradations`
  reaches the SSE wire with no consumer in `ui-next/` or `main.py`.

Nothing in the range is a regression; every change leaves the tree better than
it found it. But two commits assert work that was not done, and one CRITICAL
silent-billing gap sits three lines below a handler the same commit fixed.

Verdict: **APPROVED WITH CHANGES**, with C-1, C-2, C-3 and H-1 blocking merge.

---

## 2. Plan compliance matrix

Scope note: P1 (`cd98935`), P3 (`779586c`) and P4 (`4935ec1`) landed before this
range and were not re-verified.

### P2 - one exception tree, translated at the boundary

| Plan item | Status | Evidence | Notes |
|---|---|---|---|
| P2.1 `core/exceptions.py` becomes the only tree | Complete | `core/exceptions.py:119-207`: `ProviderError` plus six subclasses, each with `retryable` | **Deviation**: names differ from the plan's (`RateLimitError` not `ProviderRateLimited`, etc.). Existing names reused; hierarchy and `.retryable` semantics as specified |
| P2.2 one `_translate` per adapter family | Complete | `providers/openai_compat.py:44`; raised at :251, :404, :454 | **Deviation**: takes `model` as well as `exc` |
| P2.3 router catches `ProviderError`, nothing else | Complete | `router.py:609` `except ProviderError as exc:` | |
| P2.4 `ports.BaseLLMProvider` removed | Complete | grep for `class BaseLLMProvider` over `llm/` returns only `base.py:113`; `MockLLMProvider` had zero users, confirmed by grep across `tests/` | |
| P2.5 compat aliases emit `DeprecationWarning` | Complete | `llm/exceptions.py:38`; `base.py:31` `class LLMError(ProviderError)` | Independently confirmed: `LLMError` really is inside the tree the router catches |
| P2.6 contract forbidding `class .*Error` under `infrastructure/` | Complete, by a different mechanism | `test_layer_boundaries.py::test_infrastructure_defines_no_new_exception_classes`, an AST sweep with a two-way allowlist of 10 entries | **Deviation, documented in-file**: import-linter reasons about imports and has no notion of a class definition. Stronger than specified: deleting an allowlisted error forces deleting its line |
| P2 verification files | Partial | `test_llm_cancelled_error.py` (+101), `test_provider_router_degradation.py` (+61), `test_defect_hunt_fixes.py` (+93) | The two file names the plan asks for do not exist; equivalent coverage lives in the three above. `test_every_provider_facing_error_is_reachable_from_provider_error` checks the real subclass relationship, not a mock |

### P5 - silent degradation

| Plan item | Status | Evidence | Notes |
|---|---|---|---|
| P5.1 contract: WARNING log | Complete | `core/degrade.py:69`; `test_logs_at_warning_not_debug` asserts `levelno == logging.WARNING` | |
| P5.1 contract: increment `reasoner_degradation_total{site=...}` | **Partial** | Counter at `infrastructure/metrics.py:61-65`, incremented `core/degrade.py:76` | **No test asserts it.** grep for the counter name across `tests/` returns `No matches found`. See H-2 |
| P5.1 contract: append to `PipelineState.degradations` | Complete | `domain/pipeline_state.py:149`, registered as `PipelineField("core")` at :373 | Additive and defaulted; `--resume` on older state files loads |
| P5.1 "the SSE serializer surfaces it" | **Partial** | In the `done` payload at `api/execution/pipeline.py:676` and the state export at `renderers/_shared.py:343`. Zero references in `ui-next/src` and in `main.py` | See H-3 |
| P5.2 `degraded(site, fallback, *, exc, state) -> T` | Complete | `core/degrade.py:38-46`, plus an optional `detail` | 45 call sites in 24 modules |
| P5.3 ratchet, exact-equality both directions | **Partial** | `silent_failure_ratchet.py:128` fails above MAX, :131 below; wired at `ci-local.sh:57` and `test.yml:260` | The mechanism is correct; **its detection is not complete**. See H-1. **Deviation**: plan says `--max 97`; landed at 95, now 58 |
| P5.4 route sites through existing mechanisms | **Partial** | 45 sites converted | Three sites the range's own commit messages claim to have fixed are not fixed: C-1, C-2, C-3 |
| P5.5 `flows/runner.py` sets `is_fatal` for `ProviderError` subclasses | Complete | `runner.py:141-142`; `core/exceptions.py:290-304`; six parametrised cases | Independently confirmed wired into both phase drivers (`runner.py:141,153` and `api/execution/pipeline.py:474`) |

### Out of plan scope, landed in this range

| Change | Commit | Assessment |
|---|---|---|
| Benchmark engine carries forward unmeasured dimensions | `e637536` | Correct for what it covers: a suite that returned nothing. Does not cover the partial-failure case, which is C-2 |
| Untracked-path cleanup, `VISION_MODELS.md` audit | `6f8f761`, `ea93825` | Housekeeping, requested separately |
| `cached_quota_repo.py` duplicate deleted | `ba862ce` | Verified dead and verified broken as described: the deleted twin called `.model_dump_json()` on a frozen dataclass; the surviving `persistence/` copy hand-builds `json.dumps` |

---

## 3. Architecture compliance

**Dependency rule holds.** `core/degrade.py` imports the Prometheus counter
lazily and function-local (`degrade.py:74`), with the reason at the call site,
and the edge is registered in `ALLOWED_LINEAGE` in
`tests/architecture/test_layer_boundaries.py`. Same shape as the pre-existing
`core/search.py` exception.

**Import-linter count unchanged in substance.** `.importlinter` lost exactly one
line, the `ignore_imports` entry for the deleted `infrastructure.cached_quota_repo`.
Ratchet at 59, passing.

**Hexagonal boundary strengthened.** P2 moves the error vocabulary into `core/`
and leaves adapters translating at the edge. The AST test makes that enforceable
rather than aspirational.

**One boundary observation, not a violation.** `api/saas_router.py:244` passes a
`SimpleNamespace(degradations=[])` as `state=`, using the helper's duck-typed
parameter. Deliberate (`degrade.py:44` types it `Any | None`) and pinned by
`test_state_is_optional_and_a_bad_state_never_raises`, but it means the contract
is "anything with a `.degradations` list".

---

## 4. Code quality findings

**Where the conversions are right.** The range distinguishes three cases, which
is the distinction the plan turns on: signal and continue (`degraded()`); narrow
the type where the exception is the expected answer (`_wait_for_health`, the
base64 probes); and leave counted where the exception *is* the return value
(`neuro/providers.py`'s four `health_check` sites, with the reason recorded).
Getting this wrong in either direction is the main risk in a change of this
shape.

**Where it is wrong.** In three places the range emits the signal and then
returns the dangerous value anyway, and the added comment says so without the
code acting on it. `spend_limit_service.py:71-73` is the clearest:

> "The caller reads it as permission to skip the per-run ceiling entirely, so an
> import that breaks for any other reason silently unbinds that cap."

That comment is accurate, and the code then returns `False`, unbinding the cap.
Documenting a hazard is not fixing it, and a reader of the commit message would
believe otherwise. See C-3.

**Observability.** 45 sites now have a stable dotted identity where they had
none. This is the change's real contribution and it is substantial.

**Documentation.** Comments explain why, not what, and several carry falsifiable
claims. One of those claims turned out to be false — see M-1, where
`start_all.py`'s comment asserts a subclass relationship that Python does not
have.

**Security.** Nothing touches auth, sanitisation, or the prompt-injection
boundary. `saas_router.py`'s deletion path now reports what it could not delete
instead of returning unconditional success, covered by
`tests/unit/test_saas_delete_account_evidence.py`, which explicitly guards
against the mock-wiring mistake that made its own first version vacuous.

---

## 5. Testing and coverage

**Volume.** 11 new test files, roughly 1200 lines.

**Full suite at HEAD:**
```
4264 passed, 83 skipped, 4 xfailed, 51 warnings in 399.49s (0:06:39)
[exited with code 0]
```

**Mutation check run during this audit.** Disabling `e637536`'s guard
(`if samples <= 0:` changed to `if False:`):
```
FAILED tests/unit/test_benchmarks.py::TestZeroSampleDimensionsAreNotMeasurements::test_a_dead_suite_does_not_land_as_a_zero
FAILED tests/unit/test_benchmarks.py::TestZeroSampleDimensionsAreNotMeasurements::test_an_unmeasured_dimension_keeps_its_last_real_score
FAILED tests/unit/test_benchmarks.py::TestZeroSampleDimensionsAreNotMeasurements::test_the_gap_is_reported
3 failed, 26 passed in 30.62s
```
Three of four fail; the fourth targets a different guard and correctly survives.
Mutation reversed, working tree verified byte-identical to HEAD.

**No vacuous tests found**, on either pass. Several tests explicitly defend
against a previously-vacuous version of themselves.

**But one test's scope stops short of its own contract.**
`tests/unit/test_spend_cap_enforcement.py:174-187`
(`test_enforcement_failure_never_breaks_a_run`) makes `spend_tracker.record`
raise and asserts only `state._spend_cap_exceeded is False`. Every sibling test
in that file asserts on `state.degradations` or on a WARNING. The omission is
what let C-1 ship: the test proves the run survives, and never asks whether the
survival left a trace.

**Gaps.**

1. The metric leg has no test (H-2).
2. Three branches documented in commit messages as untested: the psutil kill
   branch, the POSIX-only `setrlimit` branch (`preexec_fn` does not run on
   Windows, where the suite runs), and the spend-cap preflight branch.
3. No test asserts `degradations` survives serialisation to a client.

---

## 6. Risk and regression analysis

**Architectural regressions: none.** The range removes a duplicate module, a
duplicate provider base, and three of four exception trees.

**Backward compatibility.**

- `PipelineState.degradations` is additive with `default_factory=list`, read via
  `getattr(..., [])` at every consumer.
- `base.LLMError` and `llm/exceptions.py` survive as deprecating aliases inside
  the new tree.
- **Behaviour change, intended and user-visible**: `runner.py:142` now ends a run
  on `ProviderCreditsExhaustedError` or `AuthenticationError` where it previously
  synthesised over the missing phases.
- **Behaviour change, intended**: `e637536` alters what the capability registry
  receives for a suite that returned nothing.

**Technical debt introduced.**

- `api/streaming.py` sits at exactly its pinned 337-line cap.
- 10 ruff findings in `scripts/run_all_presets.py`, ungated (`scripts/` is
  outside the ratchet's `src/` scope).
- 58 counted swallow sites remain by design — plus an unknown number of
  DEBUG-and-fall-through sites the ratchet cannot see (H-1).

---

## 7. Required corrections

Severity uses the template's scale. **Blocking** marks what should not merge.

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| **CRITICAL, blocking** (C-1) | `src/reasoner/infrastructure/llm/executor.py:756-757` | `_enforce_spend_caps` ends in `except Exception: logger.debug("Spend cap enforcement failed", exc_info=True)`. `state: PipelineState` is the first parameter (:720). Commit `7c586ab`, titled "a spend guard that has stopped guarding now says so", converted the two handlers inside `_halt_on_cap` (:774, :806) and left this one. Any exception before `_halt_on_cap` is reached — `spend_tracker.record()` throwing on a Redis hiccup, a `KeyError` in subject resolution — disables the cap for that call with no WARNING, no metric, no `degradations` entry. The run keeps making paid calls with enforcement off | Convert to `degraded("executor.spend_cap_enforce", None, exc=exc, state=state)`. Extend `test_enforcement_failure_never_breaks_a_run` to assert `state.degradations` is non-empty. Correct or amend `7c586ab`'s message |
| **CRITICAL, blocking** (C-2) | `infrastructure/benchmarks/suites/*.py` (e.g. `coding.py:53`), `benchmarks/engine.py:96` | Every suite returns `sample_count=total` where `total = min(calls_per_suite, len(_PROMPTS))` — attempted, not succeeded. A suite whose every judge call raised gives `valid=0`, `score=0.0`, `sample_count=5`. `engine.py:96`'s guard is `if samples <= 0`, so it never fires, `measured_samples` grows, and `0.0` is persisted via `update_capabilities` into the registry `UtilityScorer` reads. Commit `71acaaf` is titled "an outage no longer scores as a measured incapability"; the outage still scores as a measured incapability. Its own new test's docstring concedes this: "The score is still 0.0 — what changed is that the run now says why" | Return `sample_count=total - failed` so a fully-failed suite reaches `engine.py`'s existing `samples <= 0` path and gets the carry-forward `e637536` already built. Note that `runner.py:123` derives budget from `sample_count`, so check spend accounting before changing its meaning. Correct `71acaaf`'s message |
| **CRITICAL, blocking** (C-3) | `application/services/spend_limit_service.py:73, 182, 274`; `api/dependencies.py:708` | Three billing lookups signal and then return the permissive value: `pricing_data_available()` returns `False`, which short-circuits the per-run cost ceiling at :228; `_preset_routing()` returns `{}`, which reads downstream as "this run is free"; `_required_tier()` returns `SubscriptionTier.FREE`, which makes every preset look available on every plan. `check_run_allowed` has one call site, `api/execution/pipeline.py:157`, in the real per-run path before any spend. The mitigating comment at :274 cites `api/dependencies.py::check_preset_access` as "the primary entitlement gate" — **that function has zero production callers** (grep across `src/` returns only its own definition; the only other hits are in `tests/test_bugfixes_regression_round2.py`) and its own body says it is "deliberately not enforced" | Fail closed, or make the caller distinguish "could not price" from "free". At minimum delete the false "second line of defence" claim from the comment, because it currently tells the next reader a check exists that does not run |
| **HIGH, blocking** (H-1) | `scripts/silent_failure_ratchet.py:57` | `_SWALLOW_RE = re.compile(r"^(pass|return\b.*?)(\s+#.*)?$")` matches only `pass` and `return ...` as the first statement. A body of `logger.debug(...)` with implicit fall-through satisfies none of the three contract requirements and is invisible to the count at any `--max`. Verified: running the ratchet lists `executor.py` lines 229, 259, 529, 812 and **not** 756, which is C-1 | Add a third pattern for a handler whose body neither re-raises nor calls `degraded()` and whose only statement is a sub-WARNING log. Expect the count to rise; land the new number as the new MAX in the same change, which is what the ratchet's own contract requires |
| **HIGH** (H-2) | `src/reasoner/core/degrade.py:75-77` | Leg 2 of the contract is untested and self-concealing: the counter increment sits inside `except Exception: logger.debug(...)`, and grep for `REASONER_DEGRADATION_TOTAL` across `tests/` returns `No matches found`. If that import breaks, the metric stops at all 45 sites, evidenced only by DEBUG — the D11 pattern, inside the helper built to prevent it | Assert the counter advances across a `degraded()` call. Log the metric failure at WARNING once per process rather than DEBUG per call |
| **HIGH** (H-3) | `ui-next/src/**`, `src/reasoner/main.py` | `degradations` reaches the SSE `done` payload and has no consumer: zero references in `ui-next/src`, zero in `main.py`'s console output. Contrast the sibling field `errors`, which round-trips fully — read in `chat/page.tsx:794,1038`, stored in Zustand, persisted in `db.ts:46`, rendered in `PhaseRenderer.tsx:86` and exported by `markdown.ts:1175-1177`. The justification repeated across these commits, "the state field tells the person reading the answer", is not true of any surface a person reads | Add `degradations?: string[]` to the done-event type and render it near the epistemic labels; mirror the `errors` round trip |
| **HIGH** (H-4) | `application/orchestrator.py:144, 237` | `preflight(self, req, initial_state: PipelineState \| None = None, ...)` reads `initial_state` at :155, then calls `degraded("orchestrator.spend_cap_preflight", None, exc=exc)` at :237 without `state=`. First turns pass `None`, so nothing is lost there; **every follow-up turn** passes a real `PipelineState` that becomes the run's canonical state (`execute()`: `state = initial_state or PipelineState(...)`). The degradation fires and never reaches `degradations` | One line: `state=initial_state`. The adjacent `_fallback_buffer` capture-and-replay pattern already solves the same problem two lines below |
| **MEDIUM** (M-1) | `src/reasoner/start_all.py:216` | The narrowing comment claims "urllib.error.URLError and the socket timeouts are all OSError, so nothing that means 'still starting' escapes." Verified false: `issubclass(http.client.HTTPException, OSError)` is `False`, and `IncompleteRead.__mro__` is `(IncompleteRead, HTTPException, Exception, BaseException, object)`. A server mid-startup sending a partial response now crashes `main()` where it was previously retried. `URLError` is covered | `except (OSError, http.client.HTTPException):`, and correct the comment |
| **MEDIUM** (M-2) | `hypergate/sub_agents/method_classifier.py:141`, `tie_breaker.py:74` | `_parse_result` handles the exception internally, so `SubAgentOutput.error` stays `None` — the field `hyperagent.py:294` and `:399` already use to tell a failure from a genuine low-confidence opinion. The "TieBreaker failed" branch at :399 is unreachable for parse failures. Routing outcome is unaffected today because confidence is baked to `0.0` in both fallback dicts, so this is latent | Set `error` on the returned output, or record why the existing mechanism was bypassed |
| **MEDIUM** (M-3) | `neuro/sessions.py:536-572` | `_read_jsonl` / `_read_jsonl_gz` return `[]`, which `get_recent_context()` (:433-449) feeds straight into bootstrap context. A corrupt or locked session file is indistinguishable from a session with no history. The comment says so; no `PipelineState` exists at this layer, so only the operator-side signal is available | Return a sentinel the caller can distinguish, or have `get_recent_context()` propagate "unknown" rather than "empty" |
| **LOW** (L-1) | `api/streaming.py:311-329` | Narrowing to `except json.JSONDecodeError` left `ev.get("type")` and `collected.append(ev)` outside any handler. `sse_utils.py:_event()` always serialises a dict, so this cannot currently fire — a real reduction in protected scope, not a live bug | Note or restore the outer guard |
| **LOW** (L-2) | `application/services/event_emission_service.py:131-148` | `except RuntimeError` is correct for the production bus (`publish` is `async def` in both the impl and the Protocol), but `__init__` accepts `bus: Any`, so a plain `Mock()` would raise `TypeError` past the "never raises" contract. No production caller does this | Type the parameter, or widen the catch |
| **LOW** (L-3) | `infrastructure/benchmarks/suites/__init__.py:36` | Site label is `f"benchmarks.{suite.suite_name}"`. **Cardinality risk cleared on review**: `degrade.py:76` passes only `site` to `.labels()`; `detail` reaches the log and `state.degradations` only, never a Prometheus label. Remaining issue is grep-ability | Cross-reference the docstring, or enumerate the eight labels |
| **LOW** (L-4) | `scripts/run_all_presets.py` | 10 ruff findings, ungated because the ratchet scopes to `src/` | Leave; gating `scripts/` is a separate decision |

---

## 8. Final verdict

**APPROVED WITH CHANGES.** C-1, C-2, C-3 and H-1 block merge.

P2 is complete, including the one step whose named tool could not express it,
replaced by a stronger mechanism with the reason recorded in the file. P5's
mechanism is real: the helper does all three things it claims, `is_run_fatal` is
wired into both phase drivers, the exception trees are genuinely merged, and the
tests hold up under mutation.

But P5 step 4 is Partial, and the reason matters more than the count. Two
commits in this range carry titles asserting a fix that the code does not make —
the spend guard is still silent in its own outer handler, and a benchmark outage
still lands in the routing registry as a measured 0.0. In both cases the
commit's own body or its own test docstring contains the correction. A reader
trusting the log would be misled about the state of two safety-critical paths.

The ratchet that is supposed to police exactly this cannot see the shape of
swallow that C-1 is. Fixing H-1 first is the right order: it will find the
others of this shape before anyone has to review for them by hand.

One process note, since it is the most transferable finding here. The first pass
of this report was written by the author of the change and rated it APPROVED
WITH CHANGES on two minor findings. An independent adversarial pass over the
same range found three CRITICALs, all confirmed by running commands the first
pass did not think to run. The defect was not effort; it was that the reviewer
already believed the commit messages.
