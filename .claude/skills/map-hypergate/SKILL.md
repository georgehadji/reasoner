---
name: map-hypergate
description: Folder map of src/reasoner/hypergate — the pre-router that decides DIRECT vs WEB_SEARCH vs PIPELINE and picks the reasoning method. Use when changing routing decisions, fast-path regexes, sub-agent prompts, or the opaque method taxonomy.
folders:
  - src/reasoner/hypergate
---

# src/reasoner/hypergate — Folder Map

**Purpose:** Every request passes through HyperGate before any pipeline runs. Five focused sub-agents run in parallel, each with one narrow job and its own tiny prompt; `HyperGateAgent` synthesises their outputs into a `GateDecision` with no extra LLM call, escalating to `TieBreaker` only on conflict or low confidence. Real method names are never shown to an LLM — sub-agent prompts use an opaque letter taxonomy (B–T).

## Files

| File | What it does |
|------|--------------|
| `__init__.py` | Package exports. |
| `base_sub_agent.py` | `BaseSubAgent` — abstract base every sub-agent extends: one narrow system prompt, own model, LRU caching, fail-safe fallback. |
| `gate_agent.py` | `GateAgent` + `GateDecision` — older single-call lightweight gate (taxonomy + system prompt + `_extract_json`). Kept alongside HyperGate. |
| `hyperagent.py` (20KB) | `HyperGateAgent` — parallel Phase-1 fan-out, synthesis, TieBreaker escalation, `_WRITING_INTENT` / `_is_creative_writing` fast paths, `_failed_output` fallback. |
| `models.py` | Frozen dataclasses for the sub-agent protocol: `SubAgentInput`, `SubAgentOutput`, `HyperContext`. |

## sub_agents/

| File | What it does |
|------|--------------|
| `__init__.py` | Sub-agent exports. |
| `language_detector.py` | Detects input language → `{language, confidence}`. |
| `complexity_estimator.py` | simple / medium / complex reasoning-depth estimate. |
| `direct_detector.py` | Can this be answered without a pipeline? Holds `_CREATIVE_PATTERNS`. |
| `web_detector.py` | Does this need real-time/recent info only web search can give? |
| `method_classifier.py` (8.5KB) | Picks the reasoning method using the opaque B–T letter taxonomy. |
| `tie_breaker.py` | Resolves conflicts / all-low-confidence; sees the full `HyperContext`; validates action + method. |
| `image_model_selector.py` | On-demand only (image endpoint): maps an image prompt to capability family + cost tier. Not part of the parallel five. |

## Key entry points & gotchas

- Decision flow: fast-path regexes (short prompt → writing intent → realtime patterns → factual patterns) → five parallel sub-agents → synthesis → TieBreaker only if needed.
- Outcomes: `DIRECT` (instant answer, `api/execution/direct.py`), `WEB_SEARCH`, or `PIPELINE` with a chosen method.
- Never put real method names into a sub-agent prompt — the letter taxonomy in `method_classifier.py` and `tie_breaker.py` is deliberate. Adding a method means adding a letter, not a name.
- Every sub-agent must fail safe: a failed sub-agent returns a low-confidence output, never raises into the request path (`_failed_output`).
- `gate_agent.py` and `hyperagent.py` are two generations of the same idea — check which one the caller uses before editing.
- Sub-agent results are LRU-cached in `base_sub_agent.py`; identical prompts skip the LLM call.
