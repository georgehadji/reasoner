---
name: map-domain
description: Folder map of src/reasoner/domain — PipelineState, the 48-preset registry, pricing, credits, SaaS entities, ACR routing value objects, and the Unicode watermark domain. Use when changing pipeline state fields, presets/model routing, cost/credits logic, or watermark scrubbing.
folders:
  - src/reasoner/domain
---

# src/reasoner/domain — Folder Map

**Purpose:** Pure business entities and declarative configuration. No HTTP, no database, no third-party APIs — everything here is deterministic and testable in isolation. The two heaviest files, `pipeline_state.py` and `preset_registry.py`, are the canonical state model and the routing configuration for all 48 presets.

## Core state & presets

| File | What it does |
|------|--------------|
| `__init__.py` | Package exports. |
| `pipeline_state.py` (31KB) | **The canonical state model.** `PipelineState` (~60 fields) plus sub-containers `MethodState`, `CostTrackingState`, `ConversationState`, `PipelineCore`, `PipelineMeta`, `PipelineRemainder`, `PhaseOutput`, `PipelineField`. |
| `core_types.py` | Phase-level dataclasses: `SubProblem`, `Assumption`, `Decomposition`, `SolutionCandidate`, `CritiqueScore`, `ReviewHypothesis`, `EvidenceBundle`, `PlanContract`, `StressTestResult`, `ScenarioType`. |
| `models.py` | Small enums/registries: `TaskType`, `ClaimLabel`, `PerspectiveType`, `PerspectiveRegistry`. |
| `preset_core.py` (12KB) | `PipelinePreset` dataclass, validation, `build_auto_preset`, `get_method_from_preset`, `get_preset_tier`, `get_preset_price_tier`. |
| `preset_registry.py` (71KB) | **All 48 preset configs** — `PRESETS`, `get_preset`, `list_presets`, `invalidate_preset_cache`. Per-preset model routing per phase plus fallback chains. |

## Cost, billing, SaaS

| File | What it does |
|------|--------------|
| `pricing.py` | `ModelPricing`, per-token pricing DB, OpenRouter catalogue load, `get_pricing`, `calculate_model_cost`, `format_cost`. |
| `credits.py` | Prepaid credit currency: `CreditBalance`, `CreditLedgerEntry`, `CreditReason`, `usd_to_credits`, `InsufficientCreditsError`, overdraft ceiling. |
| `spend_limits.py` | Per-tier LLM spend ceilings: `TierSpendLimits`, `ANONYMOUS_SPEND_LIMITS`, `limits_for_tier`. A run's cost is unbounded by construction, so this caps it. |
| `saas.py` | `User`, `Subscription`, `SubscriptionTier/Status`, `UsageQuota`, `QuotaResult`, `QueryAuditLog`. |
| `api_keys.py` | User-owned key domain: `ApiKey`, `GeneratedKey`, `generate_key`, `hash_key`, namespaces (`rsn_live_*`), per-user key cap. |

## ACR (adaptive capability routing) value objects

| File | What it does |
|------|--------------|
| `model_capabilities.py` | `ModelProfile`, `ModelCapabilities`, `ModelConstraints` (Phase 2). |
| `task_requirements.py` | `TaskRequirement`, `TaskConstraints` (Phase 3). |
| `scoring_weights.py` | `ScoringWeights` plus `BUDGET_/BALANCED_/PREMIUM_WEIGHTS`, `get_weights_for_tier` (Phase 3). |
| `telemetry.py` | `LLMCallTelemetry`, `ModelRoleStats` (Phase 1). |
| `harness_metrics.py` | Scorecard value objects: `PhaseMetrics`, `PresetScorecard`, `HarnessScorecard`, `HarnessMutation`, `ReplayResult`, `PromotionRecord`. All-default fields for `--resume` compatibility. |

## Article pipeline

| File | What it does |
|------|--------------|
| `article_domain.py` (20KB) | Immutable article-pipeline model: `Ok`/`Err` result types, `Claim`, `Verdict`, `VerifyMethod`, `HumanDecision`, `Threshold`, `GatePolicy`, `claim_support_ratio`. |

## watermark/ (Layer A — Unicode mark scrubbing, pure domain)

| File | What it does |
|------|--------------|
| `__init__.py` | Layer A public surface; bottom of the import-linter layer stack — imports nothing outside itself. |
| `marks.py` | Carrier taxonomy: `MarkKind`, `MarkConfidence`, codepoint classifiers (private-use, variation selector, tag char, glue, CJK, Mongolian). |
| `layer_a.py` | The implementation: `inspect_text()` / `scrub_text()` sharing one scan; flag-sequence, bidi, tag-run scanning; `Action`, `Decision`, `ScanIndex`. |
| `rules.py` | Context-dependent preservation rules (specification pattern): bidi, emoji glue, CJK variation selector, script joiner, flag tag, same-script filler. |
| `spans.py` | `detect_protected_spans` — never scrub inside code fences, inline code, URLs, or markdown link targets. |
| `report.py` | Frozen report objects: `CharHit`, `TextInspectReport`, `ScrubStats`, `ScrubResult`. |
| `divergence.py` | Bigram-Jaccard lexical divergence for Layer B rewrite candidates; `select_most_diverged`. |

## Key entry points & gotchas

- Method-specific state uses `dict[str, Any]` with `field(default_factory=dict)`. **Always access via `.get()`**, never direct subscript — this is what keeps `--resume` working with older state files.
- `PRESETS` is built at module import time in `presets.py`, which is why `preset_core.py` imports `core/ports/model_registry_port.py` — the one accepted import-linter exception. Don't add more.
- Adding a preset: edit `preset_registry.py` (config) and validate against `preset_core.py` rules. Every method needs a Budget and a Premium tier.
- Cross-lab/bloc diversity is enforced by preset validators: generators must span two or more blocs, synthesis and scoring must differ in bloc.
- `pricing.py` is per-token, not per-million — don't "fix" the scale.
