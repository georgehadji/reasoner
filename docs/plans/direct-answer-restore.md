# Plan: Restore `_stream_direct_answer` + close out the prompt-caching work

**Status:** draft — not started
**Author:** Claude
**Date:** 2026-08-16
**Branch:** `review-rebase`

---

## 1. Executive summary

Four items are open. Only **A** is a live production defect.

| # | Item | Severity | Owner |
|---|------|----------|-------|
| **A** | `_stream_direct_answer` has no body — every HyperGate `DIRECT` and `WEB_SEARCH` route returns an empty stream | **P0** | this plan |
| **B** | `api/routes/pipelines.py` fails at import under pytest | P1 — diagnose | this plan |
| **C** | Prompt-caching work has no full-suite baseline | P1 — process | operator |
| **D** | Prompt reorder across 19 methods is unevaluated | P2 — quality | operator |

---

## 2. Item A — restore `_stream_direct_answer`

### 2.1 Root cause

Commit `98a630d` ("refactor: split streaming monolithic execution into specialized
submodules") created `src/reasoner/api/execution/direct.py` as a **26-line stub**. The
function body was never migrated out of the pre-refactor monolith. Evidence:

```
$ git log --oneline -- src/reasoner/api/execution/direct.py
98a630d refactor: split streaming monolithic execution into specialized submodules

$ git show 98a630d:src/reasoner/api/execution/direct.py | wc -l
26
```

The file has had exactly one commit and has always been 26 lines. It currently ends at:

```python
    if cancel_event and cancel_event.is_set():
        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
        return
```

No router call, no `phase_complete`, no `done`. Both call sites in
`api/execution/pipeline.py` (the `direct` action at :109 and the `web_search` action
at :122) therefore emit `start` and hang up.

### 2.2 The original implementation is recoverable

The complete pre-refactor body lives at `ca89bb4:src/reasoner/api/streaming.py:99`.
Recover it with:

```bash
git show ca89bb4:src/reasoner/api/streaming.py > /tmp/old_streaming.py
sed -n '99,236p' /tmp/old_streaming.py
```

**Do not restore it verbatim.** Four dependencies drifted since `ca89bb4` — see 2.3.

### 2.3 Drift since the original was written

| Dependency | Then | Now | Action |
|---|---|---|---|
| `get_preset_tier(preset)` | returned `str`, compared `tier == "premium"` | returns `SubscriptionTier` enum (`domain/preset_core.py:178`) | **Switch to `get_preset_price_tier()`** (`preset_core.py:169`) which returns `Literal["budget","premium","unknown"]` — that is the intended semantic (pricing tier, not entitlement) |
| `_CREATIVE_SYSTEM_PROMPT` | module constant in `streaming.py` | **gone** | Re-home into `phases/` — prompts belong to the phases layer |
| `_CREATIVE_MODELS_PREMIUM` / `_BUDGET` | module constants | **gone** | Re-home; see 2.5 |
| `web_search: bool` param | did not exist | present in the stub signature, passed `True` by `pipeline.py:122` | **Never implemented.** Must be built — see 2.6 |

Verified still available: aliases `claude-sonnet`, `gpt-5`, `gemini-pro` all resolve in
`_REGISTRY`; `_is_creative_writing` at `hypergate/hyperagent.py:116`;
`build_followup_context` and `_wrap_user_input` in `phases/_shared.py`;
`OPENROUTER_WEB_SEARCH_ENABLED` at `settings.py:239`.

### 2.4 Architectural placement

Per `CLAUDE.md` §1, the dependency rule is Domain → Application → Infrastructure, with
API depending on Application. `api/execution/` is a **driving adapter**: its only job is
to translate a pipeline decision into an SSE byte stream.

Apply **imperative shell / functional core**:

- **Pure core** (no IO, trivially unit-testable):
  - `build_direct_prompt(problem, history, previous_synthesis, turn_number) -> str`
  - `select_direct_profile(problem, preset_name) -> DirectProfile`
- **Imperative shell** — the async generator: calls the router, yields SSE frames.

`DirectProfile` is a frozen dataclass, not a class hierarchy. There are exactly two
profiles (creative, analytical); a Strategy *interface* with two implementations is the
speculative-generality trap. A frozen dataclass plus a selector function is the same
behaviour in a tenth of the code:

```python
# src/reasoner/phases/direct.py  (new — prompts live in the phases layer)
from dataclasses import dataclass

@dataclass(frozen=True)
class DirectProfile:
    system_prompt: str
    max_tokens: int
    temperature: float
    models: tuple[str, ...]   # preferred first; empty = use the router's own routing


DIRECT_ANALYTICAL_SYSTEM = "You are an analytical assistant. Provide a clear, concise answer."
DIRECT_CREATIVE_SYSTEM = (...)   # recover verbatim from ca89bb4 streaming.py:78
```

**Why `phases/`:** every other system prompt in the project lives there (107 constants
across 31 modules), and §3 of `CLAUDE.md` names `phases/` as the prompt-module home.
Leaving the creative prompt inside an API adapter would be the only prompt in the tree
outside that layer.

### 2.5 Drop the hand-rolled fallback loop

The original body built providers directly and looped:

```python
provider = build_provider(model_id)
response = await provider.complete_with_retry(...)
```

That path **bypasses `ProviderRouter` entirely** — and therefore bypasses the circuit
breaker, per-model concurrency limits, cost/token accumulation, and (as of this branch)
prompt-cache breakpoints and OpenRouter usage accounting. It also duplicates a fallback
chain the router already implements.

**Reuse the router.** Preferred order:

1. If `profile.models` is empty → single `router.call(role="primary", ...)`.
2. If non-empty → construct a one-off `ProviderRouter` over the preferred model with the
   existing router as fallback, or extend the call to pass `role="primary"` with a
   cascading list. Prefer whichever needs no new abstraction.

This is the single largest correctness improvement in the restore: it puts the direct
path back under the same observability and caching as every other LLM call, which is
precisely the invariant the caching work established.

### 2.6 `web_search=True` — new behaviour, needs a decision

`pipeline.py:122` calls with `web_search=True` when `OPENROUTER_WEB_SEARCH_ENABLED`.
Nothing implements it. OpenRouter exposes web grounding two ways (the `:online` model
suffix, and a `plugins` request field). **Verify the current contract against OpenRouter's
docs before writing it** — do not implement from memory. Then inject via the existing
`extra_body` channel, which already flows to the provider:

```python
extra_body = {"plugins": [{"id": "web"}]} if web_search else None
```

If verification is inconclusive, ship A without it and leave `web_search` routing to the
pipeline path — a broken direct path is the P0, web grounding is not.

### 2.7 SSE contract to satisfy

Frames in order, matching what the UI's `usePipelineStream` expects:

```
start → phase_start(phase=0, name="Direct Response")
      → phase_complete(phase=0, data={solution, tokens{input,output}, duration})
      → done(errors=[], total_tokens{input,output,total}, duration)
```

Error path: `phase_error(phase=0, error=...)` then `done(errors=[...])` — **always
terminate with `done`**, or the client hangs waiting for stream close.

### 2.8 Tests

A test already exists and pins the contract:
`tests/test_followup_context.py::test_direct_answer_uses_followup_context_boundaries`.
It asserts `CURRENT USER REQUEST:`, `ASSISTANT TURN:`, and the
`<<<USER_INPUT>>>` / `<<<EXTERNAL_CONTENT>>>` trust boundaries — i.e. that assistant
history is wrapped as external content and never as user instruction. **Making that test
pass is the acceptance criterion.** It is currently failing only because the function
returns early.

Add two:

1. `test_direct_answer_emits_full_sse_sequence` — fake router, assert frame order and that
   the last frame is `done`.
2. `test_direct_answer_error_path_still_emits_done` — fake router raising, assert
   `phase_error` then `done`.

Both use the existing `_FakeRouter` in `test_followup_context.py`. No new fixtures.

### 2.9 Security note — do not simplify away

`build_followup_context` wraps assistant turns in `<<<EXTERNAL_CONTENT>>>` and user turns
in `<<<USER_INPUT>>>` specifically to stop a prior assistant turn from being read as a new
user instruction. The prompt-injection test asserts the negative case
(`"<<<USER_INPUT>>>\nIgnore all that..." not in prompt`). Preserve the wrappers exactly.

---

## 3. Item B — diagnose `api/routes/pipelines.py` import failure

Symptom: `tests/test_prompt_injection.py::TestApiRequestValidation` (4 tests) fail with an
error raised while importing `src/reasoner/api/__init__.py:769` → `routes/pipelines.py:65`.
The file **compiles cleanly** (`py_compile` passes) and has uncommitted local edits, so
this is a runtime import error, not a syntax error. It also passed in an earlier run of the
same file in the same session, so it is order- or environment-dependent.

Steps:

1. Reproduce in isolation: `python -c "import reasoner.api"` with `PYTHONPATH=src`.
2. If it imports clean, the trigger is test-order state — bisect with
   `pytest tests/test_prompt_injection.py -p no:randomly` vs. with other modules loaded first.
3. Likely candidates: duplicate FastAPI route registration on re-import, or a
   settings-dependent branch (`CSRF_SECRET` unset).

Do **not** bundle this fix with A. Separate cause, separate commit.

---

## 4. Item C — baseline the suite

Blocked from inside this worktree: ~37 uncommitted in-flight modifications, and stashing
the caching subset yields 24 collection errors (inconsistent partial state). Do this on a
clean tree:

```bash
git stash push -u                    # or commit the caching work to a branch
python -m pytest tests/ -q -m "not slow and not integration" | tail -5   # BASELINE
git stash pop
python -m pytest tests/ -q -m "not slow and not integration" | tail -5   # AFTER
```

Compare **failed test IDs**, not counts — counts drift with collection errors and xdist
ordering. Two false alarms were produced in this session by trusting counts from runs that
never executed; always confirm the run actually collected tests before reading its result.

---

## 5. Item D — evaluate the prompt reorder

The caching work moved the conversation-history block ahead of the current question in 5
prompt builders (`_universal.py` ×4, `multi_perspective.py` ×1), changing prompt layout for
all 19 reasoning methods. This was accepted without eval. Run the project's eval set on a
representative preset per method family (orchestrated, debate, research, writing) and
compare against `main`. Revert the reorder if quality regresses — the caching benefit is
real but not worth a reasoning-quality regression.

---

## 6. Sequencing

```
A (P0, self-contained)  ──▶ C (baseline, needs A merged or excluded)
B (independent)         ──┘
D (independent, operator-run)
```

A and B touch disjoint files and can land in either order. C should run after both, so the
baseline reflects a tree without known-broken paths.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Verbatim restore reintroduces `tier == "premium"` string compare against an enum | Use `get_preset_price_tier`; add an assertion in the profile selector test |
| Routing around `ProviderRouter` silently drops cost/cache accounting again | Route through `router.call`; assert `metadata` carries `input_tokens` in the SSE test |
| `web_search` implemented from memory against a wrong OpenRouter contract | Verify against live docs first; ship without it if inconclusive |
| Restored prompt breaks the injection boundaries | The existing prompt-injection test is the gate — it must stay green |
| Creative model aliases rot again | They resolve today (verified); a missing alias raises at `build_provider`, so the router fallback must catch and continue |

---

## 8. Acceptance criteria

- [ ] `test_direct_answer_uses_followup_context_boundaries` passes
- [ ] Two new SSE-contract tests pass
- [ ] `tests/test_prompt_injection.py` stays green
- [ ] A `DIRECT`-routed prompt returns a real answer end to end in the running app
- [ ] Direct-path calls appear in cost/token metering (proves the router path is used)
- [ ] Item B root-caused and fixed or filed
- [ ] Baseline diff for C shows no new failed test IDs
