/**
 * Request and response shapes for the Reasoner API.
 *
 * Wire shapes keep the API's `snake_case` naming so payloads map 1:1 onto the
 * published reference with no translation layer to drift. SDK-level ergonomics
 * — client options and derived summaries — use `camelCase`.
 *
 * Optional fields are omitted from the request rather than defaulted here: the
 * server owns its defaults, and duplicating them in the SDK would let the two
 * disagree after a backend change.
 */

import type { ReasonerEvent, TokenCount, MethodAlternative } from './events.js';

/** Reasoning methods the pipeline can run. */
export type MethodId =
  | 'multi-perspective'
  | 'debate'
  | 'scientific'
  | 'socratic'
  | 'research'
  | 'jury'
  | 'pre-mortem'
  | 'bayesian'
  | 'dialectical'
  | 'analogical'
  | 'delphi'
  | 'cove'
  | 'sot'
  | 'tot'
  | 'pot'
  | 'self-discover'
  | 'writing'
  | 'brainstorming';

/** Corpus a web-grounded run should search. */
export type SourceType = 'general' | 'academic' | 'social' | 'news' | 'code';

/** A file already uploaded via `POST /api/upload`, referenced by a run. */
export interface AttachmentRef {
  file_id: string;
  filename: string;
  mime_type: string;
  extracted_text: string;
  size?: number;
}

/**
 * One step of the synthesis phase's action blueprint.
 *
 * The serializer normalises every step to these five fields, filling absent
 * ones with empty strings, so a step is never partially shaped.
 */
export interface ActionStep {
  step: string;
  action: string;
  time_horizon: string;
  go_criteria: string;
  fallback: string;
}

/**
 * Epistemic labels from the synthesis phase, keyed by claim.
 *
 * A mapping, not a list — the serializer builds it from a dict of
 * claim → label, where labels are `VERIFIED`, `HYPOTHESIS`, or `UNKNOWN`.
 */
export type ClaimLabels = Record<string, string>;

/** One turn of prior conversation, replayed into a follow-up. */
export interface ConversationTurn {
  role: 'user' | 'assistant';
  content: string;
}

/** Options for {@link ReasonerClient.run}. */
export interface RunParams {
  /** The question or problem to reason about. Required. */
  problem: string;
  /**
   * Preset name, e.g. `auto-budget` or `debate-premium`. Defaults server-side.
   * Call {@link ReasonerClient.presets} to enumerate valid names.
   */
  preset?: string;
  /** How many candidate solutions survive the critique phase. */
  top_k?: number;
  /** Run phases one at a time — slower, but kinder to rate-limited providers. */
  sequential?: boolean;
  /** Rewrite the problem statement before reasoning over it. */
  enhance_prompt?: boolean;
  /** Use the premium model routing tier for this run. */
  expert?: boolean;
  /** Ground the run in live web search. */
  web_search?: boolean;
  /** Let the router decide when web search is worth its cost. */
  smart_search?: boolean;
  /** Corpus to search when `web_search` is enabled. */
  source_type?: SourceType;
  /** Restrict web search to a single domain. */
  domain?: string;
  /** Bypass the response cache. */
  no_cache?: boolean;
  /**
   * Skip HyperGate re-classification and run `preset` as given.
   *
   * Set this when a prior {@link ReasonerClient.gate} call already resolved the
   * method, so routing is not paid for twice.
   */
  force_pipeline?: boolean;
  /** Files to reason over, previously uploaded. */
  attachments?: AttachmentRef[];
  /** Ids of previously uploaded files. */
  file_ids?: string[];
  /**
   * Idempotency key. Generated per call when omitted.
   *
   * It guards against duplicate runs and keys credit settlement, so the same
   * problem submitted twice under one id is charged once. Retries inside this
   * SDK deliberately reuse the id rather than minting a new one.
   */
  client_run_id?: string;
}

/** Options for {@link ReasonerClient.runFollowup}. */
export interface FollowupParams {
  /** The follow-up question. Required. */
  question: string;
  /** Conversation this follow-up belongs to. Required. */
  conversation_id: string;
  /** Prior turns, oldest first. Required. */
  history: ConversationTurn[];
  /** Synthesis text from the previous run, for continuity. Required. */
  previous_synthesis: string;
  preset?: string;
  top_k?: number;
  sequential?: boolean;
  enhance_prompt?: boolean;
  expert?: boolean;
  web_search?: boolean;
  smart_search?: boolean;
  agent_model?: string | null;
  attachments?: AttachmentRef[];
  file_ids?: string[];
  client_run_id?: string;
}

/** Response of `POST /api/gate` — HyperGate's decision, without executing it. */
export interface GateResponse {
  action: 'direct' | 'pipeline' | 'web_search';
  method: string | null;
  /** Concrete preset to pass back to {@link ReasonerClient.run}. */
  preset: string | null;
  confidence: number;
  reasoning: string | null;
  complexity: string | null;
  alternatives: (MethodAlternative & { preset: string | null })[];
  /** True when confidence fell below threshold and a human should confirm. */
  needs_confirmation: boolean;
}

/** Response of `POST /api/estimate` — projected cost, without running anything. */
export interface EstimateResponse {
  estimated_tokens_input: number;
  estimated_tokens_output: number;
  estimated_cost_usd: number;
  estimated_duration_seconds: number;
  preset: string;
  tier: string;
}

/** Public metadata for one preset. */
export interface PresetInfo {
  name: string;
  description: string;
  primary_id: string;
}

/** Response of `GET /api/presets`. */
export interface PresetsResponse {
  presets: Record<string, PresetInfo>;
}

/** Response of `GET /api/models` — model ids grouped by provider. */
export type ModelsResponse = Record<string, string[]>;

/** Response of `GET /api/credits`. */
export interface CreditsResponse {
  balance: number;
  tier: string;
  monthly_allowance: number;
  credits_per_usd: number;
  [key: string]: unknown;
}

/** One entry in the credit ledger. */
export interface LedgerEntry {
  reason: string;
  credits: number;
  description?: string | null;
  reference_id?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

/** Response of `GET /api/credits/ledger`. */
export interface LedgerResponse {
  entries: LedgerEntry[];
  limit: number;
  offset: number;
}

/** Response of `GET /api/credits/pricing`. */
export interface CreditPricingResponse {
  credits_per_usd: number;
  usd_per_credit: number;
  tier_monthly_allowance: Record<string, number>;
  reasons: string[];
}

/**
 * Aggregated outcome of a run, produced by {@link ReasonerClient.runToCompletion}.
 *
 * Assembled client-side by walking the stream, so it reflects exactly what the
 * pipeline emitted.
 */
/**
 * One source a web-grounded run cited.
 *
 * Left open-ended for the same reason the event union is: the server adds
 * fields without a version bump, and a closed shape would drop them.
 */
export interface Citation {
  url?: string;
  title?: string;
  source_type?: string;
  [key: string]: unknown;
}

/**
 * Wire shape of `POST /api/agent/run/sync` — a run collapsed to one JSON
 * object server-side. snake_case, matching `RunResult` in
 * `src/reasoner/api/schemas.py`; `runSync` maps this onto the same
 * {@link RunSummary} `runToCompletion` returns; see that mapping for how each
 * field lines up.
 */
export interface RunResultWire {
  preset: string;
  method: string | null;
  errors: string[];
  total_tokens: TokenCount;
  total_cost_usd: number;
  duration_seconds: number;
  synthesis: string;
  critical_insights: string[];
  open_questions: string[];
  claim_labels: ClaimLabels;
  action_blueprint: ActionStep[];
  citations: Citation[];
  models_used: string[];
}

export interface RunSummary {
  /** The synthesis text — the run's actual answer. Empty if no phase produced one. */
  synthesis: string;
  /** Non-obvious findings from the synthesis phase. */
  criticalInsights: string[];
  /** Concrete next steps from the synthesis phase. */
  actionBlueprint: ActionStep[];
  /** Questions the run could not settle. */
  openQuestions: string[];
  /** Claims tagged VERIFIED / HYPOTHESIS / UNKNOWN, keyed by claim. */
  claimLabels: ClaimLabels;
  /** Sources cited by web-grounded methods. Empty for methods that do not search. */
  citations: Citation[];
  /** Actual USD spend, as charged against credits. */
  costUsd: number;
  /** Per-phase cost breakdown. */
  phaseCosts: Record<string, number>;
  tokens: TokenCount;
  /** Wall-clock seconds the run took. */
  durationSeconds: number;
  /** Distinct models used, in first-seen order. */
  modelsUsed: string[];
  /** Recoverable errors the run reported. A non-empty list can accompany a result. */
  errors: string[];
  /** The preset the server actually ran, from the `start` event. */
  preset: string | undefined;
  /** The method actually run, after HyperGate routing. */
  method: string | undefined;
  /** Idempotency key used, whether supplied or generated. */
  clientRunId: string;
  /** Every event received, in order — for callers that need the full trace. */
  events: ReasonerEvent[];
}
