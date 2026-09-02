# V7 Defect Hunt — Rollup and Residual-Risk Register

**Date:** 2026-09-01 / 2026-09-02
**Protocol:** Autonomous Defect-Hunt Protocol V7 (Proactive), EGFV / RAR / MRADO / PCST
**Plan:** `docs/plans/backend-defect-hunt-v7.md`
**Surface:** `src/reasoner/**` (528 files, 84,988 lines). `ui-next/**` out of scope throughout.

Per-tier reports: `T1-billing-metering.md`, `T2-persistence.md`, `T3-trust-boundary.md`, `T4-llm-transport.md`, `T5-orchestration.md`, `T6-parsing-state.md`, `T7-memory-cache.md`.

---

## 1. What the hunt found

**37 confirmed defects across 7 tiers. 28 fixed, 9 escalated.**

| Tier | Surface | Confirmed | Fixed | Escalated | Cleared |
|---|---|---:|---:|---:|---:|
| T1 | billing and metering | 5 | 2 | 3 | 5 |
| T2 | persistence and event sourcing | 7 | 6 | 1 | 3 |
| T3 | trust boundary and API | 6 | 6 | 0 | 8 |
| T4 | LLM transport and routing | 9 | 8 | 1 | 4 |
| T5 | pipeline orchestration | 4 | 2 | 2 | 5 |
| T6 | parsing and state model | 3 | 2 | 1 | 4 |
| T7 | memory, cache and healing | 3 | 3 | 1 (UNKNOWN) | 4 |
| **Total** | | **37** | **28** | **9** | **33** |

33 candidates were **cleared as innocent** and are recorded per tier. That number matters as much as the confirmations: the protocol treats flagging correct code as a defect of equal severity to missing a real bug, and the innocence records exist so nobody re-raises them.

---

## 2. Open escalations, ranked

None of these are applied. Each has a written-out diff in its tier report.

| # | What | Where | Why not fixed |
|---|---|---|---|
| 1 | **Usage counters attributed to the wrong run under concurrency.** 99 of 120 concurrent calls took another call's counters, measured 82.5% | `infrastructure/llm/router.py` `_build_metadata` | Changes `_call_with_circuit`'s return type across 3 functions |
| 2 | **`WorkflowRunner` has never executed** on non-SSE runs (CLI, headless): no retries, timeouts, quality monitoring or phase events | `application/pipeline.py:492-495` | Wiring it in makes the first phase raise; `flows/runner.py` builds 4 events that do not exist, and it needs a `core/` enum addition |
| 3 | **Query quota can never deny.** `QuotaService.increment()` has zero callers in `src/` while the class is wired live | `application/services/quota_service.py:80` | Needs the metering protocol, its sink, and 5 call sites |
| 4 | **NaN and Infinity survive parsing.** `safe_float(nan)` returns 10.0, the maximum bound; a NaN clamps to probability 1.0 | `utils/json_safe.py:safe_json_loads` | Chokepoint sits outside T6's scoped surface |
| 5 | Unbilled spend on abandoned runs | `run_metering` | Needs a running cost on intermediate frames; invalidates a pinned test |
| 6 | `reset_event_store` calls async `close()` without awaiting, leaking the asyncpg pool | `infrastructure/persistence/event_store.py:853` | Other half is `api/__init__.py:280` |
| 7 | `past_due` quota re-sync missing from two branches | `application/services/billing_service.py` | Needs the adapter's tier mapping changed |
| 8 | Critic Pool `critical=True` is inert, the return is discarded | `application/flows/jury.py:70-76` | Blocked on 2 |
| 9 | `TenantManager` eviction hands a recreated tenant a different `index_lock` over the same `index.json` | `neuro/` | Both halves proven separately, could not be composed offline, so NOT promoted to CONFIRMED |

Three of these (1, 2, 4) ship a `strict=True` xfail tripwire, so the test flips the moment someone lands the fix.

---

## 3. Residual UNKNOWN set, what static analysis could not decide

**Everything PostgreSQL.** No server was available for the entire hunt. This is the single largest gap. Specifically unexecuted:

- untransacted compaction (T2)
- missing `(aggregate_id, version)` uniqueness constraint (T2)
- **a contradiction the package has with itself**: `quota_repo_postgres.py:71` and `subscription_repo.py:207` wrap `row["user_id"]` in `UUID(...)`; `credit_repo_postgres.py:101` does not. One of the two is wrong.

**Authorization on the WebSocket path.** `websocket_endpoint` never calls `_check_pipeline_ownership` (T3). Named by T3 as its own highest-value next hunt.

**Others:** orphaned reservation when the response generator is never entered (needs an ASGI disconnect harness); unkeyed admin credit grant; `/api/keys/validate` using legacy `require_auth` with no admin scope; `check_quota`'s documented allow-on-DB-error; `/api/search` forwarding provider exception text; per-preset fallback behavior; the streaming path end to end; `circuit_breaker.py` internals, never opened.

---

## 4. Surface NOT audited

Stated so the coverage claim is honest.

- **`phases/**` (36 files) and `subagents/**` (30 files)** were excluded by the plan. These are prompt-template modules; their failure mode is output quality, which is not a class in V7's taxonomy. Not "clean", **unaudited**.
- Adapters and flows individual tiers did not reach, named in their own reports.
- `healing/**` was in T7's scope and produced a finding of a different kind: **nothing under `src/reasoner/` imports `reasoner.healing`**, so it is dead code from the application's perspective.

---

## 5. Documentation found to be false

Two places where the docs asserted something the code did not do. Both corrected in place.

1. **`CLAUDE.md` claimed event-sourced replay was "verified working: snapshot + full-history replay both exercised".** No test touched either snapshot method, and both paths raised. `create_snapshot` wrote `{state, version, timestamp}`; `load_snapshot` read it back as `PipelineStateData(**data)`; those key sets have zero overlap, so every snapshot load raised `TypeError`. Corrected, with a note that "verified" in that file needs a named test behind it.
2. **Preset count.** 49, not the 48 stated.

---

## 6. Invariants: checked, not assumed

The four documented propagation-resistance invariants (`CLAUDE.md` §5) all **HOLD**, and are now backed by executed tests rather than the documentation's word. Two of them hold by *omission*, so any refactor could have broken them silently:

- recalled memory stays at user-message position, never a system prompt (T3, 2 tests)
- Phase-2 generators stay blind to each other (T3 and T5, structurally confirmed)
- `harden_system_prompt` applied at both chokepoints, `flows/services.py:89` and `subagents/base.py:101`, with the HyperGate exclusion documented at `base_sub_agent.py:160`
- model and web text stays wrapped, never interpolated raw

T3's attachment fix strengthened the fourth: attachments were the one wrapped-but-unsanitised channel.

Also verified rather than asserted:

- **`--resume` across version skew works.** 24 executed skew scenarios through the real save/load path all loaded and ran. This is the property the `.get()`-never-subscript rule exists to protect, and it had never been tested. The forward direction is not covered: a newer writer's unknown key raises `TypeError`.
- **Tenant isolation holds.** `owner` is a UUID, fixed-length and sanitizer-stable, so the `u-` and `a-` namespaces cannot collapse.
- **Preset contracts are clean** across all 49: no duplicate keys, no unknown routing or fallback roles, no models absent from the registry, no empty or self-referential chains.

---

## 7. Process notes worth keeping

- **The ruff ratchet is exact-equality, and a defect hunt lowers it.** The count fell 2249, then 2247, then 2243 as tiers removed lint incidentally while fixing defects. A drop fails the gate exactly as a rise does. Agents were told to report drift rather than edit the shared constant, because three of them editing it concurrently would have raced into a broken gate. It was set once, at the end, in both `scripts/ci-local.sh` and `.github/workflows/test.yml`.
- **Phase 6 caught a defect in a fix.** T3's first attachment fix would have silently truncated a 50 KB document to 10,000 characters. Revised once, both halves pinned by tests. This is the self-review phase earning its cost.
- **Two environmental failures were not findings.** `import-linter` died on an out-of-memory error with three agents resident, and all three agents once died on `ENOTFOUND`. Both were retried clean. Agents were told explicitly to treat these as environmental.
- **A test can hide a defect.** T4's streaming `TypeError` survived a long time because the existing test stubbed `create` as synchronous.

---

## 8. The honest claim

Regions T1 through T7 were audited for the defect classes listed in each tier report, and the 37 defects above were found and triaged. Completeness is over **defect classes examined**, not defect instances.

This is **not** a claim that the backend is sound. `phases/**` and `subagents/**` were never audited. Every PostgreSQL path is unexecuted. Nine escalations remain open, including one that corrupts billing attribution under concurrency and one that means an entire retry and timeout layer has never run.

**Highest-value next hunt:** the PostgreSQL paths, against a real server. It is the largest unexecuted surface, it holds a contradiction the package has with itself (`UUID(row["user_id"])` applied in two repos and not a third), and every finding there is currently UNKNOWN rather than cleared.
