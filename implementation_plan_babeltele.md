# Implementation Plan — BabelTele Compress→Read Capability for Reasoner

**Document type:** Architecture-aligned implementation plan
**Target system:** Reasoner (Adaptive Reasoning Architecture) v2.2
**Scope:** Introduce a *verified, safety-gated* model-native context-compression capability (“BabelTele”), with an offline optimization harness, aligned to the existing hexagonal/DDD + CQRS architecture.
**Status:** Draft for review (no code changes authorized by this document)
**Note:** Saved as `implementation_plan_babeltele.md` — the name `implementation_plan.md` is already in use by the unrelated Reaper-V7 remediation roadmap (2026-06-21) and was deliberately not overwritten.

---

## 1. Executive Summary

This plan adds a **compress→read** capability to Reasoner: a compressor LLM rewrites verbose context into a dense, low-readability symbolic form (“BabelTele”), and a reader LLM consumes it — reducing context-window pressure in long-document QA, agent memory, and multi-agent message passing.

The capability is genuinely useful but carries **two load-bearing risks** that dictate the entire sequencing:

1. **Security — injection-filter bypass.** Symbolic compression is an obfuscation channel that defeats Reasoner’s regex-based `sanitize_for_prompt()` injection defense. Compression of *untrusted* input cannot ship until a semantic re-gate exists.
2. **Correctness — unverifiable losslessness.** “No information lost” is not provable in general. We replace certainty with a **layered verification stack** (deterministic guards → atomic-claim recall → bidirectional entailment) plus **fail-safe fallback to the original**.

Accordingly, the rollout is **safety-and-verification-first**: the runtime path is built so that compression is *opportunistic and the original is authoritative* — any verification or safety failure rejects the compressed form and falls back to uncompressed context. The feature ships **off by default**, **opt-in per preset**, **trusted content first**, and **never on a structured-output (JSON) contract**.

**Phases:** (0) Foundations & guardrails → (1) Safety + Verification → (2) Core capability behind flag + cost observability + offline eval MVP → (3) Optimization (best-of-N → prompt search) → (4) Productionization (Neuro memory, multi-agent, GA).

**Headline non-goal (YAGNI):** we are *not* attempting a universal codebook, activation-level analysis, or a learned compressor. BabelTele is a black-box prompting capability validated empirically per compressor–reader pair.

---

## 2. Current Architecture Assessment

### 2.1 Relevant existing structure

| Concern | Existing asset | Path |
|---|---|---|
| Role-based LLM routing + fallback + circuit breaker + **per-call token/cost metadata** | `ProviderRouter` | `infrastructure/llm/router.py` |
| Flow contract (phases as `PhaseStep`, `WorkflowServices.call_llm`) | `WorkflowStrategy` / `PhaseStep` | `application/flows/base.py` |
| Method→flow registry | `WorkflowFactory` | `application/flows/factory.py` |
| Preset definitions (`method`/`primary_id`/`routing`/`tags`) | `_REGISTRY` | `domain/preset_registry.py` |
| Cross-lab diversity routing | per-role model assignment | `domain/preset_registry.py` |
| Input sanitization / prompt-injection regex | `sanitize_for_prompt()` | `infrastructure/.../sanitization.py` |
| Structured-output parsing | `parsing.extract_json()` | `infrastructure` |
| Feature-flag pattern (`os.getenv(...).lower() in (...)`) | `Settings` | `core/settings.py` |
| **Existing compression flags** (prior art) | `TOKEN_CONTEXT_COMPRESSION`, `TOKEN_PROMPT_COMPRESSION`, `TOKEN_NEURO_COMPRESSION`, `COMPACTION_ENABLED` | `core/settings.py` |
| Tiered long-term memory | Neuro L1/L2/L3 + `smart_compress` | `neuro/` |
| Resume-safe method state | `dict[str, Any]` + `.get()` access | `domain/pipeline_state.py` |

### 2.2 Architectural fit and constraints

- **Dependency rule (must hold):** the new flow lives in the **application** layer and depends only on **core ports** (`LLMPort`) — never on `infrastructure` directly. Deterministic verification guards (number/entity extraction) are **pure** and belong in a domain/core service. LLM-judged verification (claim recall, NLI) is an **application service** behind a port.
- **Prompt modules** belong in `phases/` (BabelTele compress prompt, read prompt, verification prompts), consistent with the existing prompt modules.
- **Preset addition** must pass `scripts/validate_presets.py` and respect cross-lab diversity.
- **Resume compatibility:** new state goes in `PipelineState.method_state["babel"]` accessed via `.get()` — backward-compatible with `--resume` of older state files (a project invariant).
- **No schema/DB migration** is required for Phases 0–3 (compression is in-flight). Persisted compression (Neuro) is deferred to Phase 4 and treated as a separate, migration-aware change.

### 2.3 Technical-debt / risk touchpoints (pre-existing, to avoid worsening)

- Known dependency-rule violations exist (`domain/preset_core.py` → `infrastructure.llm.registry`; `api/streaming.py` bypasses CQRS). **Do not** add new violations; route the new flow through the existing `WorkflowFactory`/services seam.
- Regex-based injection defense is the weak link this feature stresses — the plan hardens it with a semantic re-gate rather than extending brittle regexes.
- **Interaction with the Reaper-V7 roadmap:** that plan’s D1 (cache key omits `user_id`) and C2 (idempotency) touch the same request path. Coordinate so BabelTele caching/keying inherits the D1 fix rather than re-introducing a tenant-leak via a compressed-blob cache.

---

## 3. Detailed Implementation Plan (Phased Roadmap)

> Sequencing principle: **nothing that touches untrusted input or acts on decoded content ships before its safety/verification gate exists.** Compression is always *fail-safe to original*.

| Phase | Milestone | Key deliverables | Exit gate |
|---|---|---|---|
| **0 — Foundations & guardrails** | Capability scaffold exists, inert | Feature flag (`BABELTELE_ENABLED`, default off); `compress_read` method registered in `WorkflowFactory`; `phases/_babeltele.py` prompt module; **output-contract isolation policy** (compression forbidden on JSON-emitting roles); offline eval dataset fixtures | Flag-off no-op verified; CI green; no behavior change |
| **1 — Safety + Verification (prerequisite)** | A compressed blob can be trusted or rejected | `VerificationService` (deterministic guards → claim recall → bidirectional NLI); `SafetyReGate` (sanitize-first + decoded-intent injection check); **fail-safe gate to original** | Injection corpus blocked; number/entity preservation enforced; gate falls back on any failure |
| **2 — Core capability (trusted, flagged) + observability** | `CompressReadFlow` runs end-to-end on trusted content | `CompressReadFlow` (2 `PhaseStep`s); `babeltele-budget`/`-premium` presets (opt-in); **net-efficiency metric** + logging/metrics/tracing; offline eval harness MVP (accuracy-retention) | Frontier measured on golden set; net-efficiency reported; 80%+ coverage |
| **3 — Optimization** | Frontier improved & pair-validated | Best-of-N compression sampling against the reward; cross-lab **transfer matrix**; reconstruction-as-substrate-discriminator; **denoising metric**; (optional) prompt search | Validated compressor–reader pairs allow-list produced |
| **4 — Productionization** | GA for sanctioned use cases | Neuro memory integration (migration-aware); multi-agent message compression (trusted only); docs (`AGENTS.md`, `ARCHITECTURE_MINDMAP.md`); staged rollout | Canary metrics within thresholds; sign-off |

---

## 4. Task Breakdown Structure (WBS)

### WS-E1 — Compress→Read core capability (Enhancement)

- **Objective:** Provide a `compress_read` method that compresses trusted context then answers from the compressed form, behind a flag and preset.
- **Affected components:** `application/flows/compression.py` (new `CompressReadFlow`), `application/flows/factory.py` (register), `phases/_babeltele.py` (new prompts), `domain/preset_registry.py` (new presets), `core/settings.py` (flag), `api/serializers.py` (phase serializers).
- **Design changes:** Two `PhaseStep`s — `compress` (role `compressor`) and `read` (role `reader`). State in `method_state["babel"] = {blob, src_tokens, ratio, verification, fallback_used}`. Router roles `compressor`/`reader` resolved via preset `routing`.
- **Implementation tasks:** (1) prompt module; (2) flow with two phases calling `services.call_llm`; (3) capture `metadata["input_tokens"|"output_tokens"]`; (4) register method + presets; (5) serializers; (6) flag default-off no-op.
- **Refactoring:** None invasive — additive. Reuse `WorkflowServices`; do not bypass CQRS/factory seam.
- **Testing:** unit (flow phase transitions, mocked `ProviderRouter`); integration (end-to-end with stub providers per `reasoner-testing`); resume test (`method_state` round-trip).
- **Acceptance criteria:** Flag-off ⇒ method unavailable/no-op. Flag-on + preset ⇒ produces an answer; phases stream; `--resume` works.
- **Rollback:** Flip `BABELTELE_ENABLED=false`; preset removal. No migration.

### WS-F1 — Lossless-verification stack (Fix: silent information loss)

- **Objective:** Convert “no info lost” from an unprovable claim into a **measured, bounded, gated** risk.
- **Affected components:** `domain/verification/` (pure deterministic guards), `application/services/verification_service.py` (LLM-judged layers via `LLMPort`), `phases/_babeltele.py` (reconstruction + claim prompts).
- **Design changes:** Layered, short-circuiting verifier returning a `VerificationReport(passed, claim_recall, missing_entities, hallucinated_claims, score)`:
  1. **Deterministic guards (pure):** extract numbers, dates, units, named entities from the original; assert each appears or is entailed in the compressed form. No LLM. Catches dropped digits/sign flips/missing entities.
  2. **Atomic-claim recall:** decompose original into atomic claims; verify each is entailed by the blob → quantified recall.
  3. **Bidirectional NLI:** `original ⊨ reconstruction` **and** `reconstruction ⊨ original`; the second direction flags **hallucinated** reconstruction (the key failure mode where a strong decoder invents dropped facts).
- **Implementation tasks:** deterministic extractor + matcher; claim extractor/judge prompts; NLI prompts; report model; thresholds in `constants_limits.py`.
- **Refactoring:** Reuse `sanitize`/parsing utilities; ensure judge runs on a **different model** than the compressor (cross-lab) to avoid self-collusion.
- **Testing:** property tests (every number/entity in original recoverable or rejected); golden cases of known lossy compressions must FAIL; hallucinated-reconstruction fixtures must be caught by reverse NLI.
- **Acceptance criteria:** Any missing number/entity ⇒ `passed=False`. Claim recall below threshold ⇒ fail. Reverse-entailment violation ⇒ fail.
- **Rollback:** Verifier is a pure add-on; disabling it forces fallback-to-original (safe direction).

### WS-F2 — Safety harness (Fix: prompt-injection obfuscation bypass)

- **Objective:** Ensure symbolic compression cannot smuggle injected instructions past Reasoner’s defenses.
- **Affected components:** `application/services/safety_regate.py`, `CompressReadFlow` (wiring), reuse `sanitize_for_prompt()`.
- **Design changes:**
  - **Sanitize-first ordering:** original NL is sanitized **before** compression.
  - **Untrusted-blob posture:** the compressed blob is treated as untrusted regardless of source.
  - **Decoded-intent re-gate (semantic, not regex):** before the reader’s answer is acted upon / before the blob enters any downstream prompt, decode intent and run an **LLM-judge injection check** + re-run `sanitize_for_prompt()` on the decoded text.
  - **Output-contract isolation:** compression is **forbidden** on any role whose output is parsed by `extract_json()` (enforced by policy + a guard that raises if a `compressor`/`reader` role is mapped onto a structured-output phase).
  - **Trust tiers:** `trusted` (system’s own reasoning/memory, controlled docs) vs `untrusted` (raw user input, external agents). Untrusted compression requires the re-gate to pass; on any doubt → fallback to original.
- **Implementation tasks:** re-gate service; trust-tier field on the compression request; policy guard for output-contract isolation; injection-judge prompt.
- **Testing:** **security suite** — a curated prompt-injection corpus compressed via BabelTele must be caught by the decoded-intent re-gate; assert no symbolic payload reaches a downstream prompt un-gated; assert structured-output phases reject compressor/reader role mapping.
- **Acceptance criteria:** 100% of the injection corpus either blocked or routed to fallback; zero structured-output contamination.
- **Rollback:** Flag-off; re-gate failure defaults to original (fail-safe). Kill switch independent of `BABELTELE_ENABLED`.

### WS-F3 — Cost accounting & observability (Fix: uncounted compression cost)

- **Objective:** Make the efficiency claim honest and monitorable.
- **Affected components:** flow instrumentation; metrics/log emitters; tracing spans around `compress`/`read`.
- **Design changes:** Compute **net efficiency = original_input_tokens − (compressor_input_tokens + compressor_output_tokens + reader_input_tokens + reader_output_delta)** using `ProviderRouter` `metadata` already returned per call. Emit per-run: ratio, net token delta, $ delta, verification score, fallback rate, latency (extra round).
- **Implementation tasks:** metric names + dashboards; structured logs; OpenTelemetry-style spans; alert on negative net-efficiency rate and high fallback rate.
- **Testing:** unit on the accounting math; integration asserting metadata captured.
- **Acceptance criteria:** Every run reports net-efficiency and fallback reason; dashboards live.
- **Rollback:** Observability is additive; no functional rollback needed.

### WS-E2 — Evaluation & optimization harness (Enhancement)

- **Objective:** Measure and improve the accuracy-retention frontier per compressor–reader pair; produce a validated-pairs allow-list.
- **Affected components:** `scripts/babeltele_eval.py` (offline, out of request path), eval datasets (QuALITY/MeetingBank-shaped fixtures).
- **Design changes (leverage order — highest payoff first):**
  1. **Knob 0 — model/ratio sweep:** fix a strong prompt; sweep `routing={compressor, reader}` across the whitelist + target ratios → frontier + **cross-lab transfer matrix** (free, via existing routing).
  2. **Knob 1 — best-of-N:** sample N compressions, keep argmax-reward (reward = QA accuracy gated by `VerificationService`, costed by metadata).
  3. **Knob 3 — prompt search (optional):** OPRO/GEPA-style over a gene decomposition, *only if* 0–1 plateau below target.
  - **Reconstruction-as-substrate-discriminator:** reuse WS-F1’s reconstruction to log whether fidelity is uniform across readers (substrate-like) or family-specific.
  - **Denoising metric:** track cases where compressed accuracy > baseline; flag as denoising **or** relative-accuracy normalization artifact (do not over-claim).
- **Implementation tasks:** harness runner; reward = accuracy + verification gate + token cost; frontier/matrix reporters; pairs allow-list output consumed by presets.
- **Testing:** harness unit tests on a tiny fixture; deterministic seeds; frontier regression baseline checked into repo.
- **Acceptance criteria:** Reproducible frontier + transfer matrix; an allow-list of validated `(compressor, reader)` pairs with measured fidelity floors.
- **Rollback:** Offline only; no runtime impact.

### WS-E3 — Productionization (Enhancement)

- **Objective:** Sanctioned GA for trusted internal compression.
- **Affected components:** `neuro/` (persisted compression, migration-aware), multi-agent message path, docs.
- **Design changes:** Use BabelTele as a **lossy index/cache over a retained original** in Neuro (never the canonical store); multi-agent compression restricted to `trusted` tier; presets ordered Budget→Premium per UI convention.
- **Implementation tasks:** Neuro adapter with original-retention guarantee; agent-message compression behind trust check; `AGENTS.md` + mindmap updates; staged rollout.
- **Testing:** memory round-trip with original recoverable; multi-agent integration; contamination guard.
- **Acceptance criteria:** Original always retrievable; canary metrics within thresholds.
- **Rollback:** Per-surface flags; revert to uncompressed memory; Neuro original retained so no data loss.

---

## 5. Risk & Mitigation Matrix

| ID | Risk | Likelihood | Impact | Severity | Mitigation |
|---|---|---|---|---|---|
| R1 | Injection payload smuggled through symbolic form past regex defense | High (if untrusted) | Critical | **Blocker** | WS-F2 sanitize-first + decoded-intent semantic re-gate; untrusted compression gated; fail-safe to original |
| R2 | Silent loss of a critical fact (number/entity) | High | High | **Blocker** | WS-F1 deterministic guards (hard fail) + claim recall; reject + fallback |
| R3 | Decoder hallucinates dropped info, masking loss | Medium | High | High | WS-F1 **reverse** NLI flags non-entailed reconstruction; cross-lab judge |
| R4 | Symbolic style leaks into a JSON-emitting phase, breaking `extract_json()` | Medium | High | High | WS-F2 output-contract isolation policy + guard; compression context-side only |
| R5 | Net efficiency negative for one-shot tasks | Medium | Medium | Medium | WS-F3 net-efficiency metric + alert; reserve for long-context/amortized agent use |
| R6 | Poor cross-model transfer (non-portable pair) | Medium | Medium | Medium | WS-E2 transfer matrix → validated-pairs allow-list; presets restricted to it |
| R7 | Eval overfitting (Goodhart) to the question set | Medium | Medium | Medium | Held-out + adversarial needle questions; reconstruction probe independent of QA |
| R8 | `--resume` breaks on new state | Low | Medium | Low | `method_state["babel"]` via `.get()`; resume test in CI |
| R9 | Added latency (extra inference round) | High | Low | Low | Track latency metric; restrict to surfaces where token savings justify the round |
| R10 | New dependency-rule violation introduced | Low | Medium | Low | Flow→ports only; verification LLM behind `LLMPort`; review gate |
| R11 | Dataset contamination inflates fidelity (memorized summaries) | Medium | Medium | Medium | Note as mechanism confound; include non-public fixtures in eval set |
| R12 | Compressed-blob cache re-introduces tenant leak (Reaper D1) | Low | Critical | High | Inherit D1 fix; include `user_id` + trust-tier in any compression cache key |

---

## 6. Testing & Quality Assurance Strategy

- **Unit (pytest, `@pytest.mark.unit`):** deterministic guards (number/entity recall), accounting math, flow phase transitions, report models. Pure functions ≥ 90% coverage.
- **Integration (`@pytest.mark.integration`):** end-to-end `CompressReadFlow` with mocked `ProviderRouter` (per `reasoner-testing` patterns); resume round-trip; serializer output.
- **Security suite (new mark `@pytest.mark.security`):** prompt-injection corpus through compress→read must be blocked or fall back; structured-output isolation enforced; no un-gated symbolic payload downstream. **CI-blocking.**
- **Property-based:** for random fact-bearing inputs, every number/entity is either preserved or the run is rejected (no silent drop).
- **Evaluation/regression:** offline frontier + transfer matrix checked against a committed baseline; alert on frontier regression. Treated as a tracked metric, not a pass/fail unit test.
- **Coverage gates:** honor existing self-healing CI gates (60% fail / 80% warn); target 80%+ on new modules.
- **TDD:** verification guards and safety re-gate are written test-first (RED→GREEN→refactor) given their criticality.

---

## 7. Deployment & Rollback Plan

### 7.1 Deployment

- **Flags:** `BABELTELE_ENABLED` (master, default `false`) + independent `BABELTELE_SAFETY_REGATE` and `BABELTELE_UNTRUSTED_ALLOWED` (default `false`). Compression on untrusted input requires *both* master and untrusted flags **and** a passing re-gate.
- **Opt-in presets:** `babeltele-budget` / `babeltele-premium` registered only after `validate_presets.py` passes; restricted to the WS-E2 validated-pairs allow-list.
- **Staged rollout:** internal trusted-content surfaces (agent memory, controlled docs) → canary → broader. Untrusted-input compression is the **last** surface, if ever, and only behind the re-gate.
- **CI/CD:** security suite + preset validation are merge gates; net-efficiency and fallback-rate dashboards live before canary.

### 7.2 Rollback

- **In-band (automatic):** any verification or safety failure ⇒ **fallback to original** — the primary, always-on rollback. No human action.
- **Out-of-band (manual):** flip `BABELTELE_ENABLED=false` (instant, no migration); independent safety kill switch; preset removal.
- **State safety:** no DB/schema migration in Phases 0–3 ⇒ rollback is a flag flip. Phase 4 Neuro change retains the original ⇒ revert cannot lose data.
- **Circuit breaker:** existing per-model breaker covers compressor/reader provider failures.

---

## 8. Post-Implementation Validation Checklist

**Functional**
- [ ] Flag-off ⇒ `compress_read` unavailable; zero behavior change elsewhere.
- [ ] Flag-on + preset ⇒ end-to-end answer produced; phases stream; `--resume` round-trips `method_state["babel"]`.

**Verification (no-info-loss bounding)**
- [ ] Deterministic guard rejects any run dropping a number/date/unit/entity.
- [ ] Claim-recall computed and thresholded per run.
- [ ] Reverse-entailment catches hallucinated reconstruction fixtures.
- [ ] Verification judge runs on a different model/lab than the compressor.

**Safety**
- [ ] Injection corpus 100% blocked or routed to fallback via decoded-intent re-gate.
- [ ] `sanitize_for_prompt()` applied to original pre-compression *and* decoded intent.
- [ ] No compressor/reader role mapped onto an `extract_json()` phase (guard raises).
- [ ] Untrusted compression impossible without both flags + passing re-gate.

**Observability & cost**
- [ ] Every run emits ratio, net-token delta, $ delta, verification score, fallback reason, latency.
- [ ] Alerts armed on negative net-efficiency rate and elevated fallback rate.

**Quality & architecture**
- [ ] New modules ≥ 80% coverage; security suite is CI-blocking.
- [ ] No new dependency-rule violation (flow → ports only).
- [ ] `validate_presets.py` passes; presets respect cross-lab diversity and the validated-pairs allow-list.
- [ ] Any compression cache key includes `user_id` + trust tier (no Reaper-D1 regression).

**Documentation**
- [ ] `AGENTS.md` + `ARCHITECTURE_MINDMAP.md` updated; preset list + flags documented.

---

## Appendix A — Engineering Practices Applied

- **SOLID / Clean Architecture:** flow depends on `LLMPort` (DIP); verification split into single-responsibility layers; deterministic guards (domain) separated from LLM-judged layers (application).
- **Separation of Concerns:** compression (capability) vs verification (correctness) vs re-gate (security) vs accounting (observability) are independent, independently testable services.
- **DRY/KISS/YAGNI:** reuse `ProviderRouter`, `sanitize_for_prompt`, `extract_json`, settings-flag pattern; standalone `compress_read` method first (no premature “universal compressor”); prompt search only if cheaper knobs plateau.
- **Secure-by-Design / Defensive Programming:** fail-safe to original; untrusted-by-default blob posture; output-contract isolation; trust tiers; both-flags-required for untrusted.
- **Observability:** structured logs, metrics (ratio, net-efficiency, fallback rate, verification score), tracing spans per phase.
- **CI/CD & Review:** security + preset-validation merge gates; coverage gates; TDD on critical paths; code review per project standards.
- **Performance & Scalability:** restrict to surfaces where token savings exceed the extra round + compressor cost; best-of-N bounded; amortize in multi-turn agent settings; circuit breaker + fallback preserve availability.
