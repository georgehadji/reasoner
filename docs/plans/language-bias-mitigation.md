# Language-Induced Bias Mitigation — Implementation Plan

**Status:** Draft · **Date:** 2026-06-26 · **Owner:** TBD
**Motivation:** Buyl et al. (*npj AI* 2026, "LLMs reflect the ideology of their creators") — the *same* model shifts ideology with the **language it is prompted in**. This is an axis orthogonal to the geopolitical-bloc routing fix (see `cross-bloc-routing-fix`). Goal: make Reasoner's substantive reasoning language-invariant, and make any residual language-sensitivity *visible* rather than hidden.

Two deliverables, matching the agreed table:

| # | Approach | Bias reduction | Cost | Verdict |
|---|----------|----------------|------|---------|
| A | English pivot + translate output | High (removes variance) | ~0 | **Do this** |
| B | Cross-lingual probe on sensitive queries | High + transparent | 2× subset | Best if you want honesty about residual |

---

## 0. Current State (what already exists)

There is **already a partial English-pivot** wired into the orchestrator. It must be *extended and hardened*, not rebuilt.

| Element | Location | Behavior |
|---------|----------|----------|
| Language detection | `application/pipeline.py:328` (`detect_language`) + `_phase_fusion` (`pipeline.py:342-345`) sets `state.language` | Regex (`phases/_shared.py:detect_language`) + LLM fusion confirmation. |
| Per-phase language instruction | `phases/_shared.py:55` `get_language_instruction(state)` | Reads `state.language`, injects "Respond in {lang}" into **~25 phase modules** + `perspective_phases.py:90`. Single chokepoint. |
| Translate **in** (problem → EN) | `pipeline.py:374` `_phase_cross_language_translate_in` | DeepL (`infrastructure/translation/deepl_client.py`). Gated by `pipeline.py:207` `if state.language != "English"`. Sets `state.cross_language_state`. |
| Reasoning becomes English | `_phase_fusion` re-detects language from the now-English problem → `state.language = "English"` → all subsequent phases get "Respond in English". | Implicit pivot side-effect. |
| Translate **out** (synthesis → user lang) | `pipeline.py:402` `_phase_cross_language_translate_out` | DeepL, gated by `state.cross_language_state`. |

### Why it does not currently mitigate the bias

1. **Hard DeepL dependency → silent biased fallback.** `deepl_client.py:67-68` raises `RuntimeError` with no `DEEPL_API_KEY`. `translate_in` swallows it (`pipeline.py:399`), so `state.problem` stays in the source language, fusion detects the source language, `state.language` stays e.g. `"Greek"`, and **every phase reasons in Greek** — the exact bias-prone path. With no DeepL key configured (the current real-world default), the pivot is effectively **off**.
2. **Translate-out is incomplete.** `pipeline.py:407` only translates `final_solution.core_solution`. `critical_insights`, `action_blueprint`, `open_questions`, `meta_audit`, `sources` stay English.
3. **ISO-code bug.** `pipeline.py:406` `target_lang = source_lang.upper()` yields `"GREEK"`, but DeepL expects ISO codes (`EL`, `RU`, `ZH`). Translate-out likely 400s for most non-Latin languages even *with* a key.
4. **No method exemptions.** Creative methods (writing, brainstorming, article) should generate *natively* in the user's language, not pivot+translate (a Greek poem must be written in Greek). No such carve-out exists.
5. **No probe / no sensitivity signal.** Nothing measures residual language-divergence; HyperGate has no sensitivity sub-agent (`hypergate/sub_agents/`: language, complexity, direct, web_detector, method, tiebreaker only).

---

## Part A — English Pivot + Translate Output

**Principle:** decouple **reasoning language** (always English under pivot) from **output language** (user's language, applied only at the final translate-out). Makes the *substance* identical regardless of prompt language; language affects only presentation. Removes variance; does **not** claim neutrality (English baseline has its own tilt — that is Part B's job to surface).

### A1. Make the pivot key-independent (the critical fix)

Add an **LLM-backed translation fallback** so the pivot works with zero external keys, using the existing `ProviderRouter` / `LLMPort`.

- **Core port:** `core/ports/translation_port.py` — `TranslationPort` protocol: `async translate(text, target_lang, source_lang=None) -> TranslationResult`.
- **Infra adapters (implement port):**
  - `infrastructure/translation/deepl_client.py` — existing; make it implement the port. Preferred when `DEEPL_API_KEY` present (cheap, fast, faithful).
  - `infrastructure/translation/llm_translator.py` — **new**. Uses `ProviderRouter` with a dedicated `translation` role and a strict prompt: *"Translate faithfully. Preserve meaning, structure, markdown, citations, and `[VERIFIED]`/`[HYPOTHESIS]` tags verbatim. Do not editorialize, add, or omit."* Route to a cheap cross-bloc model (respect bloc diversity — a US model translating a CN-bloc synthesis is fine).
  - `infrastructure/translation/composite.py` — **new**. `CompositeTranslator`: try DeepL → fall back to LLM translator → fall back to identity (log a `phase_warning`).
- **DI:** select adapter in the composition root (mirrors `set_build_provider`/`set_searxng_circuit_breaker` DI used to kill core→infra imports). Application depends on `TranslationPort`, never on `deepl_client` directly.

### A2. Make reasoning-vs-output language explicit (kill the implicit side-effect)

Today the pivot relies on fusion *accidentally* re-detecting English. Make it explicit and robust.

- **Domain (`domain/pipeline_state.py`):**
  - Add `output_language: str = "English"` — the user's detected language (what the final answer is rendered in).
  - Keep `language: str` as the **reasoning language** (forced to `"English"` under pivot).
  - Add `pivot_active: bool = False`.
  - Follow the codebase invariant: any *method-specific* sub-state goes in a `dict` field accessed via `.get()` (cf. `cross_language_state`). The three scalars above are core fields and acceptable as scalars (like `language`).
- **Orchestrator (`application/pipeline.py`):**
  - At preflight/fusion: set `state.output_language = detected`; if pivot applies, `state.problem = translate_in(...)` and set `state.language = "English"`, `state.pivot_active = True`. No reliance on re-detection.
  - `get_language_instruction(state)` is unchanged — it keys on `state.language`, which is now deterministically `"English"` under pivot. **Zero edits to the ~25 phase modules.** This is the leverage of the single chokepoint.

### A3. Complete + correct the translate-out

- Replace `_phase_cross_language_translate_out` body to translate **all** user-facing `FinalSolution` fields: `core_solution`, `critical_insights[]`, `action_blueprint[].{step,action,...}`, `open_questions[]`, `meta_audit.*`, and `sources[].title` (URLs untouched). Leave `claim_labels` as enums.
- Batch into **one** LLM/DeepL call (serialize fields → translate → re-map) to keep cost ~0 and avoid N calls.
- **Fix ISO mapping:** add `core/constants` map `LANG_NAME_TO_ISO = {"Greek":"EL","Russian":"RU","Chinese":"ZH",...}`; DeepL adapter uses ISO, LLM adapter uses the human name. Unknown → skip translate-out, log warning.
- Preserve citation integrity: re-run the `pipeline.py:84-91` URL-allowlist check *after* translation (translation must not invent/alter URLs).

### A4. Method exemptions (creative = native generation)

- Pivot applies to **analytical** methods only. Exempt: `writing`, `brainstorming`, `article` (and any method whose preset sets `native_language = True`).
- Source of truth: add `pivot_eligible: bool` derivation in `application/orchestrator.py` preflight, keyed off method/preset. Exempt methods keep `state.language = output_language` (native reasoning + native output, no translate-out).

### A5. Config / preset wiring

- `core/settings.py`: `LANGUAGE_PIVOT_ENABLED: bool = True` (default on — it is ~0 cost and strictly reduces variance).
- Preset-level override field in `domain/preset_core.py` for `native_language` (creative presets set it).
- Env: `LANGUAGE_PIVOT_ENABLED=false` disables globally (e.g., for debugging in-language behavior).

### A6. Tests (Part A)

- Unit: `llm_translator` preserves markdown/citations/epistemic tags (golden fixtures).
- Unit: `CompositeTranslator` fallback order (DeepL raises → LLM path; LLM raises → identity + warning).
- Unit: ISO mapping for all 9 languages in `lang_map`.
- Integration: non-English problem with **no DeepL key** → `state.language == "English"` during phases (assert via captured prompts), `output_language == "Greek"`, final fields all Greek.
- Integration: `writing` method with Greek prompt → **no** pivot, native Greek throughout.
- Regression: English problem → byte-identical to pre-change (pivot is a no-op).

---

## Part B — Cross-Lingual Probe (sensitive queries only)

**Principle:** for ideologically-sensitive queries, *measure* whether the answer would change with language and label it — aligns with Reasoner's epistemic labeling (`VERIFIED`/`HYPOTHESIS`/`UNKNOWN`) and the paper's "map diversity, don't fake neutrality."

### B1. Sensitivity classifier

- **Fast path:** regex/keyword set (politics, governance, rights, geopolitics, religion, contested history) over the (English-pivoted) problem → `state.language_sensitive: bool`.
- **Optional LLM path:** a HyperGate sub-agent `hypergate/sub_agents/sensitivity.py` (mirrors `base_sub_agent.py` LRU pattern) returning `{sensitive: bool, axis: str}`. Run in parallel with existing 5 sub-agents (no added latency). Cheap, cross-bloc model. Wire into `hyperagent.py` orchestration + `TieBreaker` only as a flag (does not change method routing).
- **Domain:** `language_sensitive: bool = False`; `language_divergence: dict = field(default_factory=dict)` (access via `.get()`).

### B2. Probe execution (gated)

Fire only when **all**: `state.language_sensitive` AND `output_language != "English"` AND preset tier == `premium` (mirror the premium-only opt-in already used for VS critique, `perspective_phases.py:187`). Setting `LANGUAGE_PROBE_ENABLED` (default `False`) as a master switch.

- New step `application/flows/language_probe_phase.py: run_language_probe_phase(state, services)`, scheduled **after** synthesis, **before** translate-out.
- It re-runs **synthesis only** (not the full pipeline) on a shallow-cloned state whose `language` is set to the *user's* language (no pivot) — i.e. the "what would the model have concluded reasoning in Greek?" counterfactual. Reuse `run_synthesis_phase` against the clone. ~1 extra synthesis call.
- Keep both `FinalSolution`s: the English-pivot one (primary) and the in-language one (probe).

### B3. Divergence detection

- Embed both syntheses' `core_solution` via the existing **Neuro embedding** service (`neuro/` L3 embedding search already provides embeddings — reuse, do not add a new dep). Cosine distance.
- Threshold (`core/constants_limits.py`): `LANGUAGE_DIVERGENCE_COSINE = 0.15` (tune). Above → material divergence.
- Fallback if embeddings unavailable: a cheap LLM judge ("do these two assessments differ materially in conclusion or emphasis? yes/no + 1-line why"), parsed via `parsing.extract_json`.
- Store `state.language_divergence = {"score": float, "diverged": bool, "english_claim": str, "inlang_claim": str}`.

### B4. Surface the result

- If diverged: append an epistemic note to `final_solution.meta_audit` (or a new `language_note` field) and **downgrade** affected top-line claims to `HYPOTHESIS` with reason `"language-sensitive"`.
- SSE: extend the synthesis serializer (`api/serializers.py` `_ser_5`/`_ser_synthesis`) to emit a `language_divergence` block so the UI can render the ⚠️ note. Add a small `ui-next` chip in the phase-5 component.

### B5. Tests (Part B)

- Unit: sensitivity classifier precision on a labeled fixture (political vs neutral).
- Unit: divergence detector — identical texts → not diverged; opposing-conclusion texts → diverged.
- Gating: non-sensitive / English / budget-tier → probe **never** runs (assert zero extra LLM calls).
- Integration: sensitive Greek query (premium) → two syntheses produced, divergence computed, epistemic note attached when divergent.

---

## Architecture Conformance (hexagonal / DDD)

- **Dependency rule:** new `TranslationPort` in `core/ports/`; adapters in `infrastructure/translation/`; orchestration in `application/services/translation_service.py`. Application → port only; concrete adapter injected via DI (no new core→infra or application→infra static imports → keeps import-linter contract clean).
- **Domain purity:** new `PipelineState` fields are plain data; method-specific state uses `dict` + `.get()` per the resume-compat invariant.
- **Parsing/security:** all LLM responses via `parsing.extract_json`; translation inputs are internal but still pass through `sanitize_for_prompt` before re-entering any prompt.
- **Resume safety:** new fields default-valued so older saved states (`--resume`) load unchanged.
- **Cost discipline:** Part A ~0 (one batched translate-out, only for non-English); Part B premium-+sensitive-only, master-switched off by default.

## Rollout Phases

1. **A1+A2+A3+A4** (pivot hardening) behind `LANGUAGE_PIVOT_ENABLED` — ship first; immediately fixes the silent biased fallback. Verify with prompt-capture integration tests.
2. **A5+A6** config + full test matrix; flip default on.
3. **B1** sensitivity flag (no behavior change yet).
4. **B2+B3+B4** probe, premium-gated, default off; enable for a canary preset.
5. **B5** + UI surfacing; docs update (`AGENTS.md`, `ARCHITECTURE_MINDMAP.md` auto-patches counts).

## Risks / Open Questions

- **Pivot picks the English baseline tilt** — acceptable (removes *variance*; Part B surfaces residual). Document explicitly in user-facing copy.
- **LLM-translator faithfulness** — risk of editorializing during translate-out; mitigate with strict prompt + the post-translation citation/allowlist re-check, and golden tests.
- **Search-in-language** — Research method may benefit from native-language web search for local sources; pivot could hurt recall. Decide per-method (likely exempt Research's *search* sub-phase from pivot while keeping synthesis English).
- **Embedding availability** for B3 when Neuro disabled → LLM-judge fallback covers it.
- **DeepL language set** narrower than the 9 in `lang_map` (e.g. no full coverage) → CompositeTranslator's LLM fallback covers the gap.
