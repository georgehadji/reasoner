# Root-cause remediation plan

Date: 2026-09-07. Branch at time of writing: `studio-adopt` at `5c7dcd6`, which
includes `origin/main` at `f6154e8`.

Related plans, different scope: `gate-and-registry-remediation.md` (2026-08-29,
the HyperGate SSOT follow-ups) and `backend-defect-remediation.md` (2026-09-02,
the T1–T7 tier reports). This document does not repeat their items. It asks a
different question: which five underlying causes, if removed, make the most
defects impossible rather than merely fixed.

Every number here was measured on the tree above during the session that
produced it. Nothing is estimated. Where a claim is inference rather than
observation it is marked INFERENCE.

## Method

For each defect found this week, ask "what would have had to be true for this
not to happen?", then group the answers. A cause made the list if it accounts
for at least three observed defects. Causes are ordered by how many downstream
defects disappear, not by how loud any one of them was.

The defects that fed the analysis, all observed and verified:

| # | Defect | Where |
|---|--------|-------|
| D1 | `--check-endpoints` crashed on `ModuleNotFoundError: No module named 'openai'`; `continue-on-error: true` reported the step as `success` for every scheduled run since it was added | `model-catalogue.yml` |
| D2 | `integration-live` lane skipped all 477 tests when the secret was unset and reported green | `integration-live.yml` |
| D3 | The alias-honesty test passed against a 3-day-stale catalogue while `coding-premium`'s scorer 404'd on every real run | `tests/unit/test_model_alias_honesty.py`, `openrouter_models.json` |
| D4 | `NoopProvider` raised `AttributeError: 'NoopProvider' object has no attribute 'complete_with_retry'` on the first call with no API key configured | `providers/noop.py` |
| D5 | `ProviderCreditsExhaustedError` (402) escapes `ProviderRouter`; the router catches `base.LLMError` and this is `exceptions.LLMError`, an unrelated class | `base.py:189`, `router.py:601` |
| D6 | `test_unauthenticated_flood_is_eventually_refused` fails locally: 80 requests take 158.93s, the bucket refills at 1 token/sec, so no 429 can ever occur | `tests/test_t3_trust_boundary.py:90` |
| D7 | `test_deprecated_alias_still_routes` fails on any machine whose `.env` sets `DEEPSEEK_API_KEY`, including on `main` at `f6154e8` | `tests/unit/test_model_alias_honesty.py:203` |
| D8 | Six CLAUDE.md counts wrong (28/48/19/~197/350+/12 against 210/49/24/316/472/8); the adapter line named four providers that are not direct adapters | `CLAUDE.md` |
| D9 | Price comments wrong by a factor of 1000 (`$0.002/$0.006` for a `0.000002/0.000006` per-token model) on one branch, and wrong on both branches for `nemotron-3-ultra` | `registry.py` |
| D10 | Eight registry aliases answering `is not a valid model ID` or `does not exist`; one of them was `multi-perspective-budget`'s destructive generator | `registry.py`, `preset_registry.py` |
| D11 | `NEMOTRON_RERANK_MODEL` defaulted to an id absent from the catalogue; the Cohere-failure fallback issued one doomed request per document, then returned the input unchanged | `settings.py:326`, `rerank.py:274` |
| D12 | `ARCHITECTURE_MINDMAP.md` and `docs/CODEMAPS/*` stale since 2026-09-03 because the `post-commit` hook lives in `.git/hooks/`, which `core.hooksPath=.githooks` no longer reads | `.githooks/` holds only `pre-commit`, `pre-push` |
| D13 | `${{ }}` inside a shell comment invalidated an entire workflow file; `yaml.safe_load` and `check-jsonschema` both called the file valid | `integration-live.yml:86` (fixed in #67) |
| D14 | `studio-adopt` was 45 commits behind `main`, still carried D10's dead aliases, and both branches had independently implemented `reasoning_effort.py` with different ratchet constants | branch state |

---

## P1. Guards that report success without proving they ran

**Downstream defects that disappear:** D1, D2, D3, D12, D13, and the two
occasions this week when a `| tail` masked pytest's exit code.

### Root cause

There is no contract that a check must demonstrate it executed. A green step
means "the process exited 0, or we told GitHub not to care", not "the assertion
was evaluated". Four separate mechanisms each failed this way:

- `continue-on-error: true` converts any failure, including import errors, into
  `success` in the jobs API. Only the log distinguishes them (D1).
- `skipif(not OPENROUTER_API_KEY)` on every test in a lane makes the lane a
  no-op when the secret is absent, and pytest exits 0 on all-skipped (D2).
- A test that reads a bundled snapshot is only as fresh as the snapshot, and
  nothing checked the snapshot's age (D3).
- A generator wired to a hook location that git no longer consults runs never,
  and nothing checks that generated files match what the generator would
  produce now (D12).

### Fix

One pattern, applied everywhere: **every gate emits a proof marker, and a final
step asserts the markers exist.** This is the Template Method pattern applied to
CI. The skeleton (run, emit marker, verify markers) is fixed; each gate supplies
only its body.

1. `scripts/gate.py`, a small wrapper:
   `python scripts/gate.py --name endpoints -- python scripts/update_openrouter_catalogue.py --check-endpoints`.
   It runs the command, captures stdout, writes `.gates/<name>.json` with
   `{"exit": 0, "ran": true, "stdout_tail": "..."}`, and re-raises the exit
   code. A gate that never runs leaves no file.
2. `scripts/verify_gates.py --expect endpoints,catalogue,alias-honesty` fails
   the job if any expected marker is missing. Runs as the last step with
   `if: always()`, never with `continue-on-error`.
3. Advisory steps keep `continue-on-error: true` but must also pass
   `--expect-stdout "<regex>"` to `gate.py`, so "ran and found nothing"
   (`all \d+ routed models resolve`) is distinguishable from "never ran".
4. Lanes gated on a secret fail the preflight, as `integration-live.yml` now
   does. Add the same preflight to `self-healing-ci.yml`, which today uses a
   placeholder key that defeats the `skipif` and then fails 398 tests with
   `401 Missing Authentication header`.
5. Generated artifacts get a drift gate:
   `python scripts/update_mindmap_meta.py && git diff --exit-code -- ARCHITECTURE_MINDMAP.md docs/CODEMAPS ui-next/src/lib/capabilities.generated.ts`.
   This replaces the dead hook with something that cannot silently stop.
6. Workflow files get a lint step that rejects `\$\{\{\s*\}\}` anywhere in
   the file. `check-jsonschema` does not catch it (D13), so a one-line grep must.
7. In `scripts/ci-local.sh`, and in every documented invocation, never pipe
   pytest into `tail`. Use `--junitxml` and read the file, or `set -o pipefail`.

### Safety

Additive only. No existing step changes behaviour until its marker is added to
the `--expect` list, so rollout can be one gate per PR. Rollback is deleting the
final verify step.

### Verification

For each workflow, a deliberate break (comment out the install step) must turn
the job red. If it stays green, the gate is not wired.

---

## P2. Four exception trees and two `BaseLLMProvider` classes in one adapter layer

**Downstream defects that disappear:** D4, D5, and the entire class of "the
router's fallback chain does not fire for this failure mode".

### Root cause

`src/reasoner/infrastructure/llm/` grew its own error taxonomy instead of
implementing the ports in `core/`. Today there are:

- `core/exceptions.py`: `ReasonerError` with a `.retryable` attribute, and
  `is_retryable()` that reads it. This is the domain tree.
- `infrastructure/llm/base.py`: `LLMError(ReasonerError)`. A second base.
- `infrastructure/llm/exceptions.py`: `LLMError(InfrastructureError)` with its
  own `.retryable` and its own `is_retryable()`. Unrelated to the first two.
- `infrastructure/llm/ports.py`: a third `LLMError(Exception)`, deleted this
  week, and a second `BaseLLMProvider` with a different `complete()` signature,
  which remains.

Consequences already observed: `ProviderRouter` catches `base.LLMError` only,
so `ProviderCreditsExhaustedError` (from the `exceptions.py` tree) escapes it
(D5) and is caught only by `except Exception` in `flows/runner.py:138`.
`core.exceptions.is_retryable` reads `.retryable` on `ReasonerError` subclasses
only, so the `.retryable = False` declared on `ProviderCreditsExhaustedError` is
never consulted; the two agree by accident. `NoopProvider` and two test dummies
subclassed the `ports` base and lacked `complete_with_retry` (D4).

INFERENCE: nobody chose this. Each tree was added by someone who did not find
the previous one, which is what happens when the infrastructure layer is
allowed to define errors at all.

### Fix

Apply the hexagonal rule the project already states: **the domain owns the
error vocabulary; adapters translate into it at the boundary.** This is the
Anti-Corruption Layer pattern, and it is one-directional.

1. `core/exceptions.py` becomes the only tree:
   ```
   ReasonerError
   └── ProviderError                (retryable: False)
       ├── ProviderRateLimited      (True)
       ├── ProviderUnavailable      (True)
       ├── ProviderTimeout          (True)
       ├── ProviderCreditsExhausted (False)
       ├── ProviderAuthFailed       (False)
       └── ProviderModelNotFound    (False)
   ```
   `is_retryable()` stays where it is and reads `.retryable`. Delete the copy in
   `infrastructure/llm/exceptions.py`.
2. One translation function per adapter family, at the boundary and nowhere
   else: `providers/openai_compat.py::_translate(exc) -> ProviderError`. It maps
   `status_code` 402 to `ProviderCreditsExhausted`, 429 to
   `ProviderRateLimited`, 404 with the vendor's "not a valid model ID" body to
   `ProviderModelNotFound`, and so on. `complete_with_retry` calls `_translate`
   once and never inspects `status_code` again. The 402 special case at
   `base.py:185` moves here.
3. `ProviderRouter._execute_call` catches `ProviderError`. Nothing else. The
   fallback chain then fires for every provider failure, which is what its
   docstring already claims.
4. `infrastructure/llm/ports.py::BaseLLMProvider` is removed. One base class,
   `base.BaseLLMProvider`, which is what the router calls. `LLMPort` in
   `core/ports/` stays as the Protocol the application layer types against.
5. Compatibility: `infrastructure/llm/exceptions.py` and `base.LLMError`
   remain for one release as aliases that emit `DeprecationWarning` on import,
   then are deleted. `grep -rn "from reasoner.infrastructure.llm.exceptions"`
   finds every caller.
6. An import-linter contract forbids `class .*Error` definitions under
   `infrastructure/`. `.importlinter` already exists; this is one more
   contract, and `scripts/count_importlinter_exceptions.py` ratchets from
   whatever the count is on the day it lands.

### Safety

The riskiest step is 3, because it widens what the router catches. Do it last,
after 1 and 2 are in and the translation is tested against recorded SDK
exceptions (fixtures, not live calls). Keep `tests/test_pool_cleanup.py` and
`tests/test_e2e_real_relationships.py` in the review set: both exercise the
fallback path.

### Verification

`tests/unit/test_provider_error_translation.py`: for each SDK exception shape,
assert the translated class and its `.retryable`. `tests/test_router_fallback.py`:
raise each `ProviderError` subclass from a stub primary and assert the fallback
is invoked or `DegradedLLMResponse` is returned. Both must pass with no network.

---

## P3. Tests that read the live environment and the wall clock

**Downstream defects that disappear:** D6, D7, and every future "passes on CI,
fails on my machine" or the reverse.

### Root cause

Two things, both structural:

- `core/settings.py` is a module-level singleton that calls `load_dotenv()` at
  import. Any test that imports anything that imports `settings` gets the
  developer's `.env`. D7 is exactly this: with `DEEPSEEK_API_KEY` set,
  `build_provider()` takes the DeepSeek-direct branch and the served model id
  changes from `deepseek/deepseek-v4-flash` to `deepseek-v4-flash`. The test is
  correct; its environment is not controlled. The same mechanism explains why
  `RATE_LIMITER_REDIS_FAILURE_MODE` defaults to `fail_closed` at `settings.py:160`
  yet the D6 run logged the fail-open fallback: INFERENCE, the local `.env`
  overrides it.
- `infrastructure/rate_limiter.py` calls `time.monotonic()` directly. D6 is a
  test that needs 80 requests to arrive faster than the bucket refills, and on
  this machine each request took 2.03s. No assertion about rate limiting can be
  made against a real clock without also asserting something about the machine.

### Fix

1. **Isolate settings in tests.** An autouse fixture in `tests/conftest.py`
   that rebuilds `Settings(_env_file=None)` and installs it through the same
   injection point the app uses. Where `settings` is imported by name
   (`from reasoner.core.settings import settings`), the fixture
   `monkeypatch.setattr`s the module attribute. Tests that need a variable set
   it explicitly with `monkeypatch.setenv` and rebuild. The developer's `.env`
   never reaches a test again.
2. **Inject the clock.** A `Clock` Protocol in `core/ports/clock.py` with one
   method, `monotonic() -> float`. `RateLimiter.__init__(..., clock: Clock = SystemClock())`.
   The default is unchanged behaviour. Tests pass a `FakeClock` and advance it.
   This is plain Dependency Injection, and the Humble Object pattern for the
   part that touches the OS.
3. Rewrite D6 to assert against the limiter with a `FakeClock` at zero elapsed
   time, so the 71st request is refused deterministically. Keep one HTTP-level
   test that the dependency is *wired* (`Depends(check_rate_limit)` is present
   on `/api/gate`), which is what the T3 finding was actually about, but make it
   inspect the route's dependencies rather than run an 80-request flood.
4. Same treatment for the other time-dependent surfaces found by
   `grep -rn "time.monotonic()\|time.time()" src/reasoner --include=*.py`:
   `circuit_breaker.py`, `token_cache.py`, the quota window. One `Clock` port,
   injected in each constructor, default system clock.

### Safety

Step 1 can break tests that were accidentally depending on `.env`. That is the
point; each such test is a D7 waiting to happen. Land step 1 alone first, fix
what turns red, then proceed. Step 2 adds a keyword argument with a default; no
caller changes.

### Verification

Run the suite twice: once with the repo's `.env` in place, once with it moved
aside. The results must be identical. Today they are not (D7).

---

## P4. Derived facts maintained by hand, kept fresh by a mechanism that had died

**Downstream defects that disappear:** D8, D9, D10 (the "id exists" half),
D11, D12, and the six wrong numbers that nearly went into `PRODUCT.md`.

### Root cause

Truth about models lives in three places that nothing reconciles: the
catalogue (`openrouter_models.json`, machine-refreshed), the whitelist
(`registry.py`, hand-edited, with prices and context sizes in *comments*), and
prose (`CLAUDE.md`, `ARCHITECTURE_MINDMAP.md`). A generator existed to patch
some of the prose from code, and it was wired into `.git/hooks/post-commit`,
which stopped being consulted when `core.hooksPath` moved to `.githooks/`.
`.githooks/` contains `pre-commit` and `pre-push` only. The generator has run
manually, on the days someone remembered, since then.

Comments cannot be tested. A price in a comment was wrong by 1000x on one branch
and by an unrelated amount on the other (D9), and both branches had passed
every check. An alias named `ling-3.0-flash-free` maps to a paid id, and an
alias named `qwen3.8-max` mapped to an id that no longer existed (D10).

### Fix

Make the catalogue the single source, derive everything else, and test the
derivation. The project already does this for `capabilities.generated.ts`;
extend the same pattern.

1. **Structured fields instead of comments.** Whitelist entries gain optional
   `price_in`, `price_out` (per million tokens, from the catalogue's per-token
   values) and `context` fields. `scripts/update_openrouter_catalogue.py` gains
   `--sync-whitelist`, which rewrites those fields from the catalogue and fails
   if an entry's `model` id is absent. Existing comments lose their numbers;
   what remains is the *reason* the alias exists, which is the only thing a
   human needs to write.
2. **A test that the fields match.** `tests/unit/test_whitelist_matches_catalogue.py`:
   for every entry, `price_in == catalogue[model].pricing.prompt * 1e6` within
   rounding. This is D9 made impossible. The alias-honesty test already covers
   the "id exists" half of D10.
3. **Resurrect the generator with a gate, not a hook.** Move `post-commit`
   into `.githooks/` so local commits regenerate, *and* add the drift gate from
   P1 step 5 so a missed local run turns CI red. The hook is convenience; the
   gate is the guarantee.
4. **Alias names that lie get a deprecation path.** `registry.py` already has
   `_DEPRECATED_ALIASES`, with `None` meaning "no drop-in replacement", and
   `PresetService` warns on use. Add `ling-3.0-flash-free` and `nex-n2-pro-free`
   pointing at honestly named aliases (`ling-3.0-flash`, `nex-n2-pro`), and let
   the existing warning run for one release before removal.
5. **CLAUDE.md counts become generated.** The six numbers corrected by hand this
   week should be patched by `update_mindmap_meta.py` the way
   `ARCHITECTURE_MINDMAP.md`'s are, with `<!-- gen:models -->210<!-- /gen -->`
   markers so the prose around them stays human. The script's `_patch()`
   helper already does exactly this for the mindmap.

### Safety

Step 1 changes the shape of whitelist entries. `build_provider()` reads only
`model`, `cls`, `env`, `base`, `extra_body`; confirm unknown keys are ignored
with `grep -n "cfg\[" src/reasoner/infrastructure/llm/registry.py` before
landing. Run the sync once, review the diff by eye, commit. From then on the
test holds it.

### Verification

`python scripts/update_openrouter_catalogue.py --sync-whitelist && git diff --exit-code src/reasoner/infrastructure/llm/registry.py`
must pass on a fresh checkout. `pytest tests/unit/test_whitelist_matches_catalogue.py`
must pass. Introduce a deliberate wrong price and confirm it fails.

---

## P5. Silent degradation as the default: 616 `except Exception`, 97 of which swallow outright

**Downstream defects that disappear:** D11 and its future siblings; the
runtime counterpart of P1, failures that happen in production and leave no
trace.

### Root cause

"Never let X crash the pipeline" was applied uniformly, without distinguishing
*degrade with a signal* from *swallow*. Measured on this tree:

```
grep -rn "except Exception" src/reasoner --include=*.py | wc -l      -> 616
... followed on the next line by pass / return None / return documents
    / return [] / return {}                                           ->  97
```

D11 is the archetype: `rerank_via_nemotron` is documented as "Returns input
unchanged on any global failure". It did, for every call, for as long as its
default model id had been absent from the catalogue, and the only evidence was
a `DEBUG`-level log line nobody reads. `flows/runner.py:138` catches
`Exception` around every phase, which is what makes D5 survivable, but it also
means a typo in a phase module degrades a run instead of failing a test. This
week's test output carried `RuntimeWarning: coroutine '...publish' was never awaited`
from `event_emission_service.py:135`, whose comment reads "Never let event
publishing crash the pipeline": the bus was broken and the pipeline did not
notice.

### Fix

Do not mass-edit 616 sites. Ratchet them down the way ruff debt is ratcheted,
and give the ones that stay a contract.

1. **A contract for swallowing.** Any `except Exception` that does not
   re-raise must do all three of: log at `WARNING` with a stable event name,
   increment `REASONER_DEGRADATION_TOTAL{site="..."}`, and append to
   `PipelineState.degradations`, a new `list[str]` field with
   `default_factory=list`, read via `.get()` like every other method-specific
   field so `--resume` on old state files still works. The SSE serializer
   surfaces it. A run that degraded says so in its output, which the
   epistemic-labelling promise already requires.
2. **A helper that enforces it.** `core/degrade.py::degraded(site, fallback, *, exc, state) -> T`,
   used as `except Exception as exc: return degraded("rerank.nemotron", documents, exc=exc, state=state)`.
   One call does all three things; the pattern is visible in a grep; the
   ratchet below counts sites that do not use it.
3. **A ratchet.** `scripts/silent_failure_ratchet.py --max 97`, wired into
   `test.yml` and `ci-local.sh` next to the ruff ratchet, exact-equality in both
   directions like that one. It counts bare swallowers (the 97). New ones fail
   CI; removing one requires lowering the constant in the same change.
4. **Use the mechanisms that already exist where they fit.**
   `DegradedLLMResponse` is the right shape for the router; `NoopExecutor` is
   the right Null Object for the sandbox; `get_circuit_breaker()` is the right
   place for repeated provider failures. The fix is not new patterns, it is
   routing the 97 through the ones already there.
5. `flows/runner.py:138` stays as the last line of defence, but once P2 lands
   the phase-level catch must set `is_fatal` correctly for `ProviderError`
   subclasses, so credits-exhausted stops the run with a clear message instead
   of producing a synthesis over missing phases.

### Safety

Step 1's new `PipelineState` field is additive and defaulted. Step 3 starts at
the measured count, so it cannot fail on day one. Steps 2 and 4 are applied
site by site, each a small PR that lowers the constant by the number of sites
it converts.

### Verification

`python scripts/silent_failure_ratchet.py --max 97` passes on the tree it lands
on. Adding `except Exception: pass` anywhere under `src/` turns CI red.

---

## Sequencing

```
week 1   P1 (gate markers, drift gate, workflow lint)    small; makes everything after verifiable
         P5 step 3 (ratchet at 97)                       one script; freezes the bleeding
week 2   P3 step 1 (settings isolation), fix what reddens
         P4 steps 1-3 (structured fields, sync, test)
week 3   P3 steps 2-4 (Clock port); P4 steps 4-5
week 4+  P2 (one tree, translation at boundary, router catches ProviderError)
ongoing  P5 steps 1, 2, 4, one site per PR, ratchet down
```

P2 is last on purpose. It is the largest change and the one most likely to
surface a fallback path nobody knew was live. It should land on a suite that P3
has made trustworthy, behind gates that P1 has made honest.

## Patterns by module, in one place

| Module | Pattern | Why this one |
|---|---|---|
| `.github/workflows/*`, `scripts/gate.py` | Template Method | The skeleton (run, mark, verify) never varies; only the body does |
| `infrastructure/llm/providers/*` | Adapter + Anti-Corruption Layer | SDK exceptions are foreign; translate once at the edge, never downstream |
| `core/exceptions.py` | Single hierarchy, `.retryable` as data | Retry policy is a property of the error, not of the caller |
| `infrastructure/rate_limiter.py`, `circuit_breaker.py`, `token_cache.py` | Dependency Injection of a `Clock` port; Humble Object | Isolates the one line that touches the OS so the rest is deterministic |
| `tests/conftest.py` | Autouse fixture rebuilding `Settings(_env_file=None)` | Tests own their environment; the developer's does not leak in |
| `registry.py`, `update_openrouter_catalogue.py` | Single Source of Truth with generated views | The catalogue is machine-refreshed; everything derived from it is testable |
| `core/degrade.py`, `PipelineState.degradations` | Result-carrying degradation; Null Object where already present | Degrade visibly or not at all; reuse `DegradedLLMResponse`, `NoopExecutor`, circuit breaker |
| `scripts/*_ratchet.py` | Exact-equality ratchet | Debt can only go down, and paying it down must be recorded in the same change |

## What this plan does not cover

- D14, the branch drift. That is a process decision (merge `main` into
  long-lived branches on a schedule, or do not keep long-lived branches). There
  are 31 remote branches today; a policy is worth more than a cleanup.
- Whether the DeepSeek-direct branch should change the served model id at all.
  P3 makes it testable; the product question is separate.
- `flows/services.py:99`, the runner-less phase path with no handler. Its own
  comment says "without runner robustness". It is a stated limitation, and P5's
  ratchet will count it if anyone adds a swallow there.

## Uncertainty

Most likely to be wrong: the INFERENCE that the local `.env` is what flips
`RATE_LIMITER_REDIS_FAILURE_MODE` off `fail_closed`. It was not read directly.
If it is something else, P3 step 1 will find it, because the test will behave
differently with `.env` removed.

Most likely to be missed: a fourth exception tree, or a fifth. Run
`grep -rn "^class .*Error(" src/reasoner --include=*.py` before starting P2,
and count.
