# High-Stakes Reliability Plan (health, law, finance)

Status: draft, 2026-11-14. Nothing here is implemented.

Goal: when a question is about health, law or money, Reasoner must
(1) never answer from a single unchecked model call, (2) never show `VERIFIED`
without an authoritative source, (3) state which jurisdiction and date the answer
holds for, (4) ask for missing decisive facts before answering, (5) say plainly
when it cannot answer and who can, and (6) prove all of this with measurements.

Labels follow CLAUDE.md: VERIFIED = checked in this repo (file cited),
INFERENCE = reasoned from code read, HYPOTHESIS = untested, `[INPUT REQUIRED]` =
a decision or fact only the owner can supply.

---

## 0. What exists, and one defect to fix first

Reusable pieces (all VERIFIED by reading the code):

| Piece | Where | Reuse for |
|---|---|---|
| Parallel one-job sub-agents + TieBreaker | `hypergate/hyperagent.py` `_run_phase1`, `_synthesize` | §1 detector |
| Regex fast paths, labelled routing corpus | `hypergate/hyperagent.py` `fast_path`, `tests/_data/hypergate_routing.jsonl` | §1 pre-check, §6 corpus |
| Regex-only classifier precedent | `application/services/sensitivity_service.py` `classify_sensitivity` | §1 pattern shape |
| Evidence promotion rule (model `VERIFIED` → `HYPOTHESIS`) | `application/services/evidence_service.py` `apply_promotion_rules` | §2 policy |
| Citation allowlist from retrieved sources | `application/flows/synthesis_phase.py` `_allowed_citation_urls`, `enforce_citations` | §2 |
| Post-synthesis hooks | `application/pipeline.py` (`_phase_post_synthesis_verify`, language probe), `flows/runner.py` `resolve_phases` (egress rewrite appended once) | §5 |
| "What I took on your word" premises section | `phases/_universal.py:247` | §4 fallback |
| Gate preview + user confirmation UI | `api/routes/gate.py`, `GateResponse.needs_confirmation`, `ui-next/.../MethodChoicePrompt.tsx` | §4 |
| Off → shadow → active rollout precedent | `JEV_MODE`, ACR `mode == "shadow"` | rollout |
| Real eval harness precedent | `benchmarks/sycophancy/` (`framing_divergence.py`, `BASELINE.md`) | §6 |

**Defect D1 (VERIFIED):** promotion caps only `FinalSolution.evidence` bundles.
`FinalSolution.claim_labels` is parsed straight from model JSON
(`synthesis_phase.py:171`) and serialized unchanged (`serializers.py:1061`), so a
model-asserted `VERIFIED` reaches the UI, the MCP tools (`api/mcp/tools.py:53`)
and the agent API (`api/routes/agent.py:211`). The labels a user sees are not
the capped ones. This applies to every run, not only high-stakes ones.

**Defect D2 (INFERENCE):** `source="search"` counts as sensor-grade
(`EVIDENCE_SENSOR_SOURCES = ("sensor", "search")`), but the model writes that
`source` field itself. Nothing checks that its `evidence_refs` are URLs the run
actually retrieved.

Fix D1 and D2 first (§2.1). They are cheap, apply to all runs, and §2 builds on them.

---

## 1. Detect high-stakes questions in HyperGate

**Layer:** `domain/` (value objects), `hypergate/` (detection), `core/` (thresholds, flag).

### 1.1 Domain model — `domain/stakes.py` (new, pure, no imports outside stdlib)

Paradigm: functional core, immutable value objects.

```python
class StakesDomain(StrEnum):  HEALTH, LEGAL, FINANCIAL, NONE

@dataclass(frozen=True, slots=True)
class Jurisdiction:
    country: str | None      # ISO 3166-1 alpha-2, e.g. "GR"
    as_of: date | None

@dataclass(frozen=True, slots=True)
class StakesProfile:
    domain: StakesDomain
    confidence: float
    jurisdiction: Jurisdiction
    missing_facts: tuple[str, ...]   # decisive facts the question lacks
    @property
    def is_high(self) -> bool: ...
```

Frozen dataclasses, not Pydantic: `domain/` stays dependency-free (Dependency
Rule, `.importlinter` contract 1).

### 1.2 Deterministic pre-check — `hypergate/stakes_patterns.py` (new)

Pattern: same shape as `sensitivity_service` — compiled regex table per domain,
pure function `match_stakes(text) -> StakesDomain`. **Multilingual** (at least
English and Greek): HyperGate runs before the language pivot, so English-only
patterns would miss Greek questions.

Wiring in `fast_path`: when `match_stakes` hits, skip the *factual-lookup → direct*
fast path (return `None` so the sub-agents run). The short-prompt and named-method
fast paths keep their order. Reason: the factual fast path is the one route that
answers with a single unchecked call.

### 1.3 LLM detector — `hypergate/sub_agents/stakes_detector.py` (new)

Pattern: Template Method, subclass `BaseSubAgent` exactly like
`WebSearchDetectorSubAgent` (ONE JOB, `_system_prompt`, `_parse_result`, `degraded()`
on parse failure with a safe default of `domain="none", confidence=0.0`).
Output schema: `{domain, confidence, country, as_of_relevant, missing_facts[], rationale}`.

- Runs as a 6th member of the `asyncio.gather` in `_run_phase1`: parallel, so no
  added latency, only one more cheap call. `HyperContext` gains `stakes_output`.
- Its prompt never names methods (CLAUDE.md §5 invariant). `HyperContext.to_dict`
  already strips `method` keys; add a test that it still does with the new field.
- Fail-safe direction: on error the regex pre-check (§1.2) still decides. A
  regex hit with a failed detector counts as high-stakes. A false positive costs
  money; a false negative costs trust.

### 1.4 Policy — pure function `apply_stakes_policy(decision, profile) -> GateDecision`

Location: `hypergate/stakes_policy.py`. Pattern: Policy / Decorator over the
decision. It is a pure function that returns a new `GateDecision` and never mutates
it, so it is table-testable without LLMs.

Rules when `profile.is_high`:
- `action == "direct"` → `pipeline`.
- `action == "web_search"` → `pipeline` with a grounded method (a single search
  answer has no critique or verification).
- Method: keep the classifier's pick if it is grounded; else route to the
  web-grounded method (Research/Prism). Add CoVE as augmentation if
  `augmentation_methods` accepts it. `[verify: the accepted augmentation set in
  _synthesize, hyperagent.py:457]`
- `GateDecision` gains `stakes: dict | None` (the serialized profile).

Called once, at the end of `HyperGateAgent.decide`, so fast paths, Jev, the
TieBreaker and `_synthesize` all pass through it. One choke point, the same
idea as `restrict_blocs()` for western-only runs.

**Decided (2026-11-14): never upgrade the tier.** A high-stakes question on a
Budget preset stays on Budget. The policy forces the grounded method within the
user's tier and changes nothing that affects price. No "Premium recommended"
prompt either. Test: a Budget preset with a high-stakes profile keeps its tier.

### 1.5 Config

- `core/settings.py`: `STAKES_POLICY_MODE: Literal["off", "shadow", "active"] = "off"`.
  In shadow mode the policy runs and logs plus a metric, and the decision is
  unchanged.
- `core/constants_limits.py`: `STAKES_CONFIDENCE_THRESHOLD`,
  `HYPERGATE_MAX_TOKENS_STAKES`. Re-check `GATE_ESTIMATED_COST_USD`: the gate now
  makes 6 calls.
- Metrics: `STAKES_DETECTED_TOTAL{domain,source=regex|llm}` and
  `STAKES_POLICY_REROUTED_TOTAL{from_action}` through the existing metrics port.

### 1.6 Tests
- `tests/unit/test_stakes_patterns.py`: Greek and English positives, near-miss
  negatives ("health bar in a game", "law of large numbers").
- `tests/unit/test_stakes_policy.py`: decision table covering every action ×
  high/low × detector failure.
- Add labelled YMYL rows to `tests/_data/hypergate_routing.jsonl`, where the
  expected outcome is "never `direct`".
- `tests/architecture`: `domain/stakes.py` imports only stdlib.

---

## 2. No `VERIFIED` without an authoritative source

**Layer:** `domain/` (authority registry), `application/services/evidence_service.py`
(policy), `application/flows/synthesis_phase.py` (call site).

### 2.1 General fixes (all runs) — D1 and D2

- `evidence_service.reconcile_labels(claim_labels, evidence) -> dict`: a claim
  label may not exceed its bundle's promoted label, and a `VERIFIED` claim with no
  bundle becomes `HYPOTHESIS`. Pure function, called in `finalize_solution` right
  after `apply_promotion_rules`, inside the same `degraded()` guard.
- `_apply_promotion` gains `allowed_refs: set[str]`. `source="search"` stays
  `VERIFIED` only when at least one `evidence_refs` URL is in
  `_allowed_citation_urls(state)`, normalized with the existing `_norm_url`.
  Otherwise the label drops to `HYPOTHESIS`.
- `language_probe_phase` downgrades `claim_labels` after this point. Its
  downgrade must stay a downgrade; add a test that reconciliation runs before it
  and that it never upgrades.

### 2.2 Authority registry — `domain/authority_sources.py` (new, declarative data)

Pattern: declarative registry, the same idea as `preset_registry.py`. Pure lookup
`authority_tier(url, domain, country) -> AuthorityTier` (`PRIMARY` = statute,
regulator, clinical guideline body; `SECONDARY` = peer-reviewed, official stats;
`NONE`).

`[INPUT REQUIRED: curated domain lists per (domain, country)]` Seed candidates to
review, not to ship unreviewed: EU (eur-lex.europa.eu, ema.europa.eu,
esma.europa.eu), GR (et.gr for ΦΕΚ, eof.gr, aade.gr, bankofgreece.gr), US
(cdc.gov, nih.gov, fda.gov, sec.gov, irs.gov), plus pubmed.ncbi.nlm.nih.gov and
who.int. Every entry needs an owner-approved review date.

### 2.3 Policy — Strategy in `evidence_service`

```python
class EpistemicPolicy(Protocol):
    def promote(self, bundle, allowed_refs) -> EvidenceBundle: ...

StandardPolicy        # today's rules + §2.1
HighStakesPolicy      # Standard + VERIFIED needs ≥1 ref with tier >= PRIMARY
                      # for profile.domain/country, else HYPOTHESIS
```

Strategy, not `if` branches, because the stakes profile picks the rule set once
per run and both sets stay unit-testable in isolation. `finalize_solution` picks
the policy from `state.stakes` and does nothing else differently.

### 2.4 Retrieval bias (search phases)

No new port. After retrieval, a pure function ranks results by `authority_tier`
so the synthesis context is built from primary sources first
(`flows/search_phases.py` and `prism_research.py`, where citations are assembled).
Query rewriting with `site:` filters is adapter-specific. It is out of scope
until §6 shows that ranking alone leaves too few primary sources.

### 2.5 Tests
- `test_evidence_reconcile.py`: D1 cases (claim without a bundle, claim above its bundle).
- `test_evidence_search_refs.py`: D2 cases (a `search` source citing an unretrieved URL).
- `test_high_stakes_policy.py`: a primary source keeps `VERIFIED`; a blog-only
  source drops to `HYPOTHESIS`; the wrong country drops to `HYPOTHESIS`.

---

## 3. Jurisdiction and "as of" date

**Layer:** `application/services/stakes_service.py` (new), `domain/pipeline_state.py`,
`phases/`.

- `PipelineState` gains `stakes: dict[str, Any] = field(default_factory=dict)`.
  It is read with `.get()` only, so `--resume` keeps working with old state files
  (Key Invariant).
- Jurisdiction resolution: **Chain of Responsibility** of small pure resolvers,
  first non-`None` wins:
  1. explicit `RunRequest.jurisdiction` (new optional field, ISO code, validated
     against a fixed set);
  2. the detector's `country` (§1.3);
  3. unresolved → marked as a missing fact for §4.
  **Decided (2026-11-14):** accounts do not store a country, so there is no
  account-default link. Do not add one in this plan.
  A chain, because each source is optional and the order is a product decision
  that will change. Each link is one function, testable alone.
- `as_of` = run date (UTC) unless the user names a date.
- Prompts (`phases/_universal.py`, `_shared.py`): one stakes block injected into
  decomposition and synthesis. The block names the jurisdiction and date and says
  "state which rules apply as of this date; name the source of each rule". It is
  wrapped with `_wrap_external_content` because it carries user-derived text, and
  `RunRequest.jurisdiction` passes `sanitize_for_prompt` (fresh user input).
- Output: `FinalSolution` gains `scope: dict = {}`
  (`{"jurisdiction": "GR", "as_of": "2026-11-14"}`), serialized in `_ser_synthesis`
  and shown as one line above the answer in the UI.

Tests: the resolver chain order, `--resume` with a state file that lacks
`stakes`, and that the prompt block is wrapped.

---

## 4. Ask before answering when decisive facts are missing

**Layer:** `api/` (gate response, run request), `application/services/gate_service.py`,
`ui-next/`.

- Source of truth: `StakesProfile.missing_facts` (§1.3), capped at 3 questions,
  deterministically trimmed.
- `decide_route` returns `stakes: {domain, missing_facts, jurisdiction_needed,
  premium_recommended}`. The existing `needs_confirmation` becomes true when there
  are missing facts and the stakes are high.
- UI: a new `FactsPrompt` component next to `MethodChoicePrompt`, using the same
  flow. It shows the questions and lets the user answer, skip, or "answer anyway".
  Follow the studio rules: tokens from `ui-next/src/styles/tokens.css` only,
  keyboard focus, WCAG 2.2 AA.
- `RunRequest` gains `facts: dict[str, str] | None`. The answers are fresh user
  input: they pass `sanitize_for_prompt` and are appended to the problem as
  user-stated premises, so the existing premise machinery
  (`_parse_premises` → "What I took on your word") labels them correctly.
- Non-interactive callers (CLI, headless, MCP, agent API) never block: missing
  facts go into `open_questions` and the premises section, and the run proceeds.
- Existing `AmbiguityDetectorSubAgent` (enhancement) only appends "Clarifications
  needed" to the prompt. Leave it alone; this flow does not reuse it, because it
  runs after the gate has already committed to a run.

**Decided (2026-11-14): "answer anyway" is allowed for every domain**, health
dosing included. The user can always skip the fact questions. When they skip,
the answer still states which decisive facts were missing (§5).

Tests: gate response schema, sanitization of `facts`, and no blocking on the
non-interactive paths. A frontend test for `FactsPrompt` beside
`MethodChoicePrompt.test.tsx`.

---

## 5. Abstain and refer, specifically

**Layer:** `application/services/answerability.py` (new, pure), post-synthesis hook,
serializer, UI.

- Pure function `assess_answerability(final_solution, state) -> Answerability`
  with `level ∈ {answer, answer_with_caveats, refer}` and `reasons: tuple[str, ...]`.
  Inputs, all available for every method:
  - the share of claims (after §2 reconciliation) that are `UNKNOWN` or `HYPOTHESIS`;
  - `verification_audit` failures (from `_phase_post_synthesis_verify`);
  - when present, the spread of `state.scores` / `state.critic_scores` (critic
    disagreement). It is absent for some methods; the function must not require it.
  Thresholds go in `constants_limits.py` and are tuned from §6 data, not guessed.
- Hook: run once in `ReasonerPipeline` right after `_phase_post_synthesis_verify`,
  only when `state.stakes` is high. It is deterministic, so it makes no LLM call.
- `refer` does not rewrite the model's prose (fragile, and it can strip content).
  Instead `FinalSolution` gains `reliability: dict = {}`, and the referral text
  comes from the synthesis prompt itself. When the stakes are high, the §3 block
  already asks for a "Who to ask and what to ask them" section; this step only
  decides how prominently the UI shows it.
- UI: a reliability banner in the synthesis renderer, driven by `reliability.level`.

Pattern note: pure assessment, with the side effects (state write, banner) at the
edge. This matches the functional-core / imperative-shell split the domain layer
already uses.

Tests: a table test over label mixes and score spreads; a method with no
`scores`; and the serializer carrying `reliability`.

---

## 6. Measure it

`benchmarks/benchmark_vs_calibration.py` is a synthetic simulation (random data),
not a measurement of real runs (VERIFIED by reading it). Do not cite it as
evidence for this work.

New `benchmarks/high_stakes/`, modelled on `benchmarks/sycophancy/`:
- `cases.jsonl`: question, domain, country, reference answer, decisive facts,
  expected route. `[INPUT REQUIRED: the reference answers must be written or
  reviewed by qualified people per domain; no model-written gold answers]`
- `run_eval.py`: real billed calls, run only through the `integration-live`
  workflow with a `-k` filter (CLAUDE.md §4). Metrics:
  1. routing recall on high-stakes cases (target: no `direct` answers);
  2. **label precision**: the share of `VERIFIED` claims that are correct against
     the reference answer (the core number);
  3. authority rate: the share of `VERIFIED` claims citing a `PRIMARY` source;
  4. refer precision and recall against cases marked "should refer";
  5. cost and latency per run versus the non-stakes path.
- `BASELINE.md` records a run with `STAKES_POLICY_MODE=off` before any §1–§5
  change ships, then one per phase.

Deterministic parts (routing corpus, policies, reconciliation) stay in the
normal unit suite. Only `run_eval.py` costs money.

---

## 7. Cross-cutting decisions

- **Personal data.** A health question can be special-category data under GDPR
  Art. 9. Today the final synthesis is saved to Neuro memory (`/neuro/learn`).
  **Decided (2026-11-14): health runs are kept out of Neuro memory.** When the
  stakes profile's domain is health, skip `/neuro/learn` for the run. Logs
  already hash the problem (hyperagent). Test: a health run makes no learn call.
- **Propagation invariants** (CLAUDE.md §5) are unaffected. All new prompt text is
  ours or wrapped. Recalled memory still never enters a system prompt. Phase-2
  generators stay blind to each other; the stakes block goes to every generator
  identically.
- **Western-only runs** keep working: §1–§5 add no provider construction. They
  use the existing router, so `restrict_blocs()` still applies.
- **Architecture gates.** Nothing in `application/` imports `infrastructure/`.
  `import-linter` contract-2 exceptions must not rise. The ruff, bandit and
  silent-failure ratchets must not rise.
- **Docs and maps.** Update `map-hypergate`, `map-domain`, `map-application`,
  `map-phases`, `map-ui-next` and `map-tests` (`/update-maps`), `AGENTS.md`, and
  `docs/ENVIRONMENT.md` (`STAKES_POLICY_MODE`).

---

## 8. Order of work

Each step is one PR, behind `STAKES_POLICY_MODE` where behaviour changes.

| # | PR | Depends on | Ships as |
|---|---|---|---|
| 1 | D1 + D2 label fixes (§2.1) | — | on for all runs (bug fix) |
| 2 | Eval harness and baseline (§6), routing corpus rows | — | tooling |
| 3 | Domain model + regex pre-check + LLM detector + policy (§1) | 1 | `shadow` |
| 4 | Authority registry + HighStakesPolicy + retrieval ranking (§2.2–2.4) | 1, 3 | `shadow` |
| 5 | Jurisdiction chain + `as_of` + prompt block + `scope` (§3) | 3 | `shadow` |
| 6 | Gate missing facts + `FactsPrompt` + `RunRequest.facts` (§4) | 3, 5 | `active` behind flag |
| 7 | Answerability + reliability banner (§5) | 1, 4 | `active` behind flag |
| 8 | Eval vs baseline; flip `STAKES_POLICY_MODE=active` | all | release |

Steps 1 and 2 are independent and can run in parallel. Step 8 needs the §6
numbers to beat the baseline on label precision with no routing regression.

## Open inputs (collected)

Decided (2026-11-14):

1. Budget → Premium upgrade: never (§1.4).
2. Stored user country: none exists, no account-default link (§3).
3. "Answer anyway": allowed for every domain, health dosing included (§4).
4. Neuro memory: health runs are kept out (§7).

Still open (no owner yet):

5. Curated authoritative-source lists and who maintains them (§2.2).
6. Reviewed reference answers per domain (§6).
