---
name: map-phases
description: Folder map of src/reasoner/phases — the prompt library. One module per reasoning method, each exporting *_SYSTEM constants and *_prompt() builders, plus shared helpers and the Verbalized Sampling stages. Use when writing or editing any LLM prompt.
folders:
  - src/reasoner/phases
---

# src/reasoner/phases — Folder Map

**Purpose:** Pure prompt construction. Every module exports `X_SYSTEM` string constants (system prompts) and `x_prompt(...)` builder functions that return user messages. No IO, no provider calls, no state mutation — the imperative shell lives in `application/flows/` and `api/execution/`. Adding a reasoning method means adding one module here.

## Shared helpers (underscore-prefixed)

| File | What it does |
|------|--------------|
| `__init__.py` | Re-exports the prompt surface. |
| `_shared.py` (12KB) | Cross-method helpers: `detect_language`, `get_language_instruction`, `build_followup_context`, `_wrap_user_input` / `_wrap_external_content` (injection fencing), `HUMANIZATION_RULES`, writing-intent indicators. |
| `_universal.py` (23KB) | Prompts every pipeline uses: disambiguation, prompt enhancement, classification (Phase 0), decomposition (Phase 1), and the shared synthesis surface. |
| `_vs_shared.py` | Shared Verbalized Sampling generation prompt + builder. |
| `_prism.py` | Prism research system prompts in speed / balanced / quality variants. |

## Method prompt modules

| File | Method |
|------|--------|
| `multi_perspective.py` | Default orchestrated flow: `PERSPECTIVE_SYSTEMS` (constructive/destructive/systemic/minimalist), critique and stress-test prompts. |
| `debate.py` | Opening, rebuttal, cross-examination, judge. |
| `jury.py` | Generator, critic, verifier, meta-eval. |
| `research.py` | Deep research (web-grounded). |
| `scientific.py` | Hypothesis generation + falsification test. |
| `socratic.py` | Elenchus question/answer pair. |
| `pre_mortem.py` | Failure imagination, backtrack, early signals, redesign. |
| `bayesian.py` | Prior, likelihood, posterior, sensitivity. |
| `dialectical.py` | Thesis, antithesis, contradictions, synthesis. |
| `analogical.py` | Abstraction, domain search, mapping, transfer. |
| `delphi.py` | Round 1 experts, aggregation, round 2 revision, convergence. |
| `cove.py` | Chain-of-Verification: draft, verify, answer, cross-check. |
| `sot.py` | Skeleton-of-Thought: skeleton, parallel solve, assemble. |
| `tot.py` | Tree-of-Thoughts: decompose, generate, evaluate, backtrack. |
| `pot.py` | Program-of-Thoughts: generate code, execute, interpret. |
| `self_discover.py` | Select, adapt, implement reasoning modules. |
| `iterative_critique.py` | Two cross-lab models debating to convergence: generator, critic, revision, synthesis. |
| `brainstorming.py` | Verbalized Sampling divergence: generate k ideas with probabilities, cluster, develop, synthesize. |
| `coding.py` (15KB) | Spec, generate, review; `_CODE_QUALITY_CONTRACT`, `strip_reasoning_from_code`. |
| `writing.py` (26KB) | Creative/long-form writing with CoVe-style draft/verify/answer/revise and hallucination guards. |
| `article.py` (27KB) | Article pipeline: retrieval plan, Sonar retrieval, draft, verify, revise. |
| `direct.py` | HyperGate DIRECT/WEB_SEARCH path: `DirectProfile`, analytical vs creative system prompts, `select_direct_profile`, `build_direct_prompt`. |

## Verbalized Sampling stages (vs_*)

| File | Stage |
|------|-------|
| `vs_decomposition.py` | `decompose_with_vs` — QueryDecompositionStage. |
| `vs_generation.py` | `generate_with_vs` — critical-path generation with NLI gate and strategies. |
| `vs_probe_generation.py` | Intent-consistency probes; `DOMAIN_PROBE_TEMPLATES`, semantic distance. |
| `vs_claim_extraction.py` | Extract claims from VS candidates. |
| `vs_coverage_audit.py` | Gap detection: paraphrase + evidence-overlap check. |
| `vs_conflict_surfacing.py` | Cross-candidate contradiction detection via NLI gate. |
| `vs_verification_routing.py` | `route_claim_by_vs_probability` — two-tier verification routing. |
| `vs_calibration.py` | `compute_vs_calibrated_confidence` from extracted signals. |
| `vs_behavioral_audit.py` | Entropy store + `log_vs_behavioral_audit` observability. |

## Key entry points & gotchas

- Naming contract: `METHOD_STEP_SYSTEM` constant plus `method_step_prompt()` builder. Flows in `application/flows/` import these by name — keep the pair together.
- Any user-supplied or externally fetched text must go through `_shared._wrap_user_input` / `_wrap_external_content` and `core.sanitization.sanitize_for_prompt` before interpolation.
- Language handling is centralized in `_shared.detect_language` / `get_language_instruction`; don't re-implement per method.
- VS sample counts (`VS_K_*`) live in `core/vs_constants.py`, not here.
- Prompts are pure strings — no `await`, no provider objects. If you need a model call, you are in the wrong layer.
