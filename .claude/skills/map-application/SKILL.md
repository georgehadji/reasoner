---
name: map-application
description: "Folder map of src/reasoner/application — CQRS application layer: ReasonerPipeline, orchestrator, per-method workflow flows and phase logic, command/query handlers, event bus, application ports, and ~60 services (adaptive routing, billing, credits, metering, serializers, renderers). Use when changing pipeline behavior, adding a reasoning flow, or touching any service."
folders:
  - src/reasoner/application
---

# src/reasoner/application — Folder Map

**Purpose:** The use-case layer. Owns pipeline orchestration (`pipeline.py`, `orchestrator.py`), one `WorkflowStrategy` per reasoning method (`flows/`), CQRS commands/queries/handlers, the domain event bus, application-side ports, and the service layer everything else calls. Depends on `domain/` and `core/` only — never on `infrastructure/` or `api/`.

## Root

| File | What it does |
|------|--------------|
| `__init__.py` | Package marker. |
| `pipeline.py` (35KB) | `ReasonerPipeline` — strategy-based orchestrator composed via `flow_factory` + `LLMExecutor` (not mixins). `timed`, `TOKEN_OPTIMIZATION`, `USE_PHASE_SUBAGENTS`. The real implementation; repo-root `pipeline.py` is a shim. |
| `orchestrator.py` (21KB) | `PipelineOrchestrator` — single entry point used by SSE, CLI, and tests. Preflight (HyperGate + preset resolution) produces `PreflightDecision`, then runs. |

## flows/ — one WorkflowStrategy per method, plus its phase logic

Convention: `<method>.py` holds the strategy class (phase sequence); `<method>_phases.py` holds the `run_*_phase` functions it calls.

| File | What it does |
|------|--------------|
| `base.py` | `WorkflowStrategy`, `PhaseStep`, `WorkflowServices` interfaces. |
| `factory.py` | `WorkflowFactory` — method name to strategy. |
| `runner.py` | `WorkflowRunner` — executes a strategy with retry/robustness. |
| `services.py` | `PipelineWorkflowServices` — concrete service bundle handed to flows. |
| `pipeline_flow.py` | Phase sequence registry/dispatcher; `PipelineFlow`, `execute_phases_dag`. |
| `multi_perspective.py` / `perspective_phases.py` | Default orchestrated method: perspectives, critique, stress test, hallucination-keyword guard. |
| `debate.py` / `debate_phases.py` | Opening, rebuttal, cross-examine, judge, evidence search. |
| `jury.py` / `jury_phases.py` | Generate, critique, verify + meta-eval, weighted ranking, recovery path. |
| `delphi.py` / `delphi_phases.py` | Round 1, aggregation, round 2, convergence, dissent. |
| `dialectical.py` / `dialectical_phases.py` (23KB) | Six strategies in one module: Scientific, Socratic, Pre-Mortem, Bayesian, Dialectical, Analogical. |
| `cognitive.py` / `cognitive_phases.py` (19KB) | CoVE, SoT, ToT, PoT, Self-Discover strategies and phases. |
| `research.py` / `research_phases.py` | Web-grounded research flow. |
| `prism_research.py` | Iterative tool-calling researcher (Prism loop): web search, scrape, uploads search, citation ranking. |
| `brainstorming.py` / `brainstorming_phases.py` | Verbalized-Sampling generate, cluster, develop, synthesis, plus prior-art search. |
| `coding.py` / `coding_phases.py` | Spec, generate, review, tests, plus library and CVE search. |
| `writing.py` / `writing_phases.py` | Source retrieval, outline, draft, fact-check, assemble. |
| `article.py` / `article_phases.py` | Article pipeline: retrieval, outline, draft, adversarial verify, structure. |
| `article_adapters.py` (23KB) | Bridges the immutable article `Context` domain to the mutable `PipelineState` phases. |
| `iterative_critique.py` / `iterative_critique_phases.py` | Generator/critic adversarial loop with `check_convergence`, `MAX_ROUNDS`, stalemate detection. |
| `augmentation.py` | Shared pre-processing: runs debate + iterative critique in parallel for deep/abstract questions, with caching. |
| `search_phases.py` (25KB) | Context vetting, result vetting, deep read, evidence validation, YouTube enrichment. |
| `synthesis_phase.py` | `run_synthesis_phase` — final synthesis. |
| `language_probe_phase.py` | Cross-lingual probe: re-runs synthesis in the native language and judges the delta. |
| `egress_rewrite_phase.py` | Layer B statistical rewrite of synthesis output (watermark scrubbing), gated by `EgressPolicy`. |

## commands/, queries/, handlers/, event_bus/

| File | What it does |
|------|--------------|
| `commands/__init__.py` | Command DTOs: `RunPipelineCommand`, `ResumePipelineCommand`, `StopPipelineCommand`, `ExecuteWidgetCommand`, `StoreMemoryCommand`, and more. |
| `queries/__init__.py` | Query DTOs: `GetPipelineStatusQuery`, `ListPipelinesQuery`, `GetHistoryQuery`, widget queries. |
| `queries/get_harness_scorecard.py` | Read-only harness scorecard query + handler. |
| `handlers/handlers.py` (20KB) | All command/query handlers: `RunPipelineCommandHandler`, `ResumePipelineCommandHandler`, `StopPipelineCommandHandler`, `ExecuteWidgetCommandHandler`, status/history handlers, `PipelineExecutionPort`. |
| `event_bus/bus.py` (19KB) | `EventBus` with subscribers, retries, rotating dead-letter file, `get_event_bus`, tracking helpers. |

## ports/ (application-side ports)

| File | Port |
|------|------|
| `auth_port.py` | `AuthPort` — Supabase and local adapters implement it. |
| `billing_port.py` | `BillingPort` — Stripe is just an adapter. |
| `billing_deadletter_port.py` | `BillingDeadLetterPort`, `FailedWebhookEvent`. |
| `email_port.py` | `EmailPort`, `EmailMessage` for event-driven notifications. |
| `quota_repository.py` | `QuotaRepository`. |
| `pipeline_ownership_port.py` | `PipelineOwnershipPort`, `OwnershipRecord`, `is_authorized` — who may read/stop/resume a run. |
| `service_protocols.py` | Protocols for `PresetService`, `PipelineService`, `SearchService`, neuro client, telemetry store. |

## services/ — pipeline, presets, output

| File | What it does |
|------|--------------|
| `pipeline_service.py` (34KB) | `PipelineService` (create/manage `ReasonerPipeline`) + `PipelineSerializationService`. |
| `preset_service.py` | Preset resolution, routing validation, router construction. |
| `search_service.py` | Web discovery, search, context vetting, result cache. |
| `recovery_service.py` | Recovery paths for problematic candidates. |
| `serializers.py` (49KB) | SSE serialization per phase: `_ser_0` through `_ser_4` plus method-specific variants. **Largest file in the layer and the SSE contract with the frontend.** |
| `renderers/__init__.py` | `RendererService` + `RenderStrategy` registry. |
| `renderers/_shared.py` (15KB) | Shared terminal/JSON rendering, `MethodType`, preset-to-method constants. |
| `renderers/_render_*.py` (16 files) | One renderer per method: multi_perspective, debate, jury, research, scientific, socratic, pre_mortem, bayesian, dialectical, analogical, delphi, cove, sot, tot, pot, self_discover. |

## services/ — ACR adaptive routing

| File | What it does |
|------|--------------|
| `adaptive_routing.py` (17KB) | `AdaptiveRoutingService` — wires capability registry + scorer + constraints into a `RoutingPlan`; `ACRSelectionLog`. |
| `utility_scorer.py` | Utility score per (model, task): capability match, quality history, cost; cold-start default. |
| `constraint_resolver.py` | Finds the best valid role-to-model assignment under all constraints. |
| `role_requirements.py` (16KB) | Default capability-weight vectors per pipeline role. |

## services/ — harness scorecard & evolution

| File | What it does |
|------|--------------|
| `scorecard_service.py` | Aggregates telemetry into harness-level metrics (read model). |
| `harness_diagnosis.py` | Ranks harness components by waste/failure. |
| `harness_guard.py` | Invariant validation for mutations; `get_model_lab`, `check_mutation_invariants`. |
| `harness_replay.py` | Sandboxed evaluation of a candidate mutation. |
| `regression_gate.py` | `GateVerdict` — passes only with no solved-case regressions. |
| `promotion_service.py` | Governed promotion; cost/safety-tier mutations require human approval. |
| `evidence_service.py` | Epistemic label promotion and evidence bundles. |
| `feedback_router.py` | Classifies execution failures into repair strategies. |

## services/ — billing, quota, auth, metering

| File | What it does |
|------|--------------|
| `credit_service.py` | Prepaid credit orchestration; a run may only start when the balance covers it. |
| `run_metering.py` | `metered()` wrapper: post-paid settlement from the terminal `done` frame; `SettlementSink`, `RunObserver`, `reserve_run_budget`. |
| `spend_limit_service.py` | Resolves and applies per-tier LLM spend ceilings; `SpendRejection`, pre-run estimates. |
| `anonymous_trial_policy.py` | Daily spend cap for anonymous runs that bypass the credit ledger. |
| `quota_service.py` | Per-tier query quotas. |
| `billing_service.py` | Checkout, portal, webhook sync. |
| `auth_service.py` | Thin cached wrapper over `AuthPort`. |
| `api_key_service.py` | Mint/list/revoke/authenticate user API keys; scope-ceiling rules. |
| `idempotency.py` | `register_run` — `client_run_id` as duplicate guard and credit idempotency key. |
| `ws_ticket.py` | Short-lived single-use WebSocket tickets (HMAC with embedded expiry). |
| `notification_subscriber.py` | EventBus subscriber sending transactional email on critical SaaS events. |
| `data_eraser.py` | GDPR erasure across event store, cache, and neuro memory. |
| `audit_service.py` | Publishes query-execution audit events off the hot path. |

## services/ — misc

| File | What it does |
|------|--------------|
| `gate_service.py` | `decide_route` — HyperGate decision shared by HTTP and MCP. |
| `estimate_service.py` | `estimate_cost`, `estimate_image_cost`. |
| `health_service.py` | `check_health` shared by HTTP and MCP. |
| `agent_results.py` | Builds one aggregated JSON result from a decoded SSE stream (`/api/agent/run/sync`). |
| `tool_schema.py` | Function-calling tool definitions projected from the request models (Anthropic + OpenAI formats). |
| `suggestions.py` | Smart search suggestions from partial queries. |
| `prism_classifier.py` | Query classifier ported from Prism. |
| `sensitivity_service.py` | Fast keyword/regex sensitivity classifier for the cross-lingual probe. |
| `egress_policy.py` | Resolves the effective watermark/provenance policy (request flag beats settings). |
| `watermark_service.py` | Facade over Layer A text scrubbing and image-metadata scrubbing. |
| `compaction_service.py` | Decides when to compact the event store; nightly loop. |
| `deadletter_replay_service.py` | Admin inspect/replay of dead-letter events. |
| `event_emission_service.py` | Domain event publishing for pipeline execution, kept out of `PipelineState`. |

## Key entry points & gotchas

- Adding a reasoning method touches six places: prompts in `phases/`, a `<method>.py` strategy plus `<method>_phases.py` here, registration in `flows/factory.py` and `flows/pipeline_flow.py`, presets in `domain/preset_registry.py`, a renderer in `services/renderers/`, and serializer support in `services/serializers.py`.
- `serializers.py` defines what the frontend receives — any field change there is a frontend-visible change.
- Services must not import `infrastructure` directly; consume the ports injected at startup.
- `orchestrator.py` and `services/preset_service.py` use `core/ports/model_registry_port.py`, injected via `set_model_registry_port()` in `api/__init__.py`, `main.py`, `headless.py`. Do not reintroduce a direct registry import — import-linter will fail.
- Billing is post-paid off the terminal SSE `done` frame: a new run entry point that skips `run_metering.metered()` runs unbilled.
