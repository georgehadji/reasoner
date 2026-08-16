/**
 * The Reasoner API client.
 *
 * Scoped to running pipelines and the metadata needed to run them well:
 * routing, cost estimation, catalogue lookups, and credit balance. API key
 * management is deliberately absent — minting credentials belongs in an
 * authenticated browser session, not in a library holding a long-lived key.
 */

import { AbortError, ReasonerError } from './errors.js';
import { isEvent, type DoneEvent, type ReasonerEvent, type TokenCount } from './events.js';
import { HttpTransport, type ClientOptions, type RequestOptions } from './http.js';
import { parseSSE } from './sse.js';
import type {
  ActionStep,
  Citation,
  ClaimLabels,
  CreditPricingResponse,
  CreditsResponse,
  EstimateResponse,
  FollowupParams,
  GateResponse,
  LedgerResponse,
  ModelsResponse,
  PresetsResponse,
  RunParams,
  RunResultWire,
  RunSummary,
} from './types.js';

const PATHS = {
  run: '/api/run',
  runFollowup: '/api/run-followup',
  runSync: '/api/agent/run/sync',
  estimate: '/api/estimate',
  gate: '/api/gate',
  presets: '/api/presets',
  models: '/api/models',
  health: '/api/health',
  credits: '/api/credits',
  creditsLedger: '/api/credits/ledger',
  creditsPricing: '/api/credits/pricing',
} as const;

const EMPTY_TOKENS: TokenCount = { input: 0, output: 0, total: 0 };

/** Generate an idempotency key, falling back when `crypto.randomUUID` is absent. */
function newRunId(): string {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') return cryptoObj.randomUUID();
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Drop undefined values so the server applies its own defaults. */
function compact<T extends object>(params: T): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) out[key] = value;
  }
  return out;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/**
 * Normalise the action blueprint.
 *
 * The serializer already fills every field, but a step arriving from an older
 * run or a partial phase should not produce `undefined` in user code.
 */
function asActionSteps(value: unknown): ActionStep[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((step): step is Record<string, unknown> => Boolean(step) && typeof step === 'object')
    .map((step) => ({
      step: asString(step.step),
      action: asString(step.action),
      time_horizon: asString(step.time_horizon),
      go_criteria: asString(step.go_criteria),
      fallback: asString(step.fallback),
    }));
}

/** Claim labels arrive as a claim → label mapping, not a list. */
function asClaimLabels(value: unknown): ClaimLabels {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out: ClaimLabels = {};
  for (const [claim, label] of Object.entries(value)) {
    if (typeof label === 'string') out[claim] = label;
  }
  return out;
}

/**
 * Client for the Reasoner API.
 *
 * ```ts
 * const client = new ReasonerClient({ apiKey: process.env.REASONER_API_KEY });
 *
 * for await (const event of client.run({ problem: 'Should we migrate off our monolith?' })) {
 *   if (isEvent(event, 'phase_complete')) console.log(event.phase, event.name);
 * }
 * ```
 */
export class ReasonerClient {
  private readonly http: HttpTransport;

  constructor(options: ClientOptions = {}) {
    this.http = new HttpTransport(options);
  }

  /**
   * Run a pipeline, yielding events as they arrive.
   *
   * The returned iterable is lazy: nothing is sent until iteration begins.
   * Leaving the loop early — `break`, `return`, or a thrown error — aborts the
   * underlying request, so a caller that stops reading stops the transfer.
   *
   * Aborting does not cancel the run server-side. The pipeline continues and is
   * still charged for what it spends; only the delivery stops.
   *
   * @throws {InsufficientCreditsError} when the balance is exhausted (402).
   * @throws {DuplicateRunError} when `client_run_id` is already in flight (409).
   * @throws {RateLimitError} when rate limited past `maxRetries` (429).
   */
  run(params: RunParams, options: RequestOptions = {}): AsyncGenerator<ReasonerEvent, void> {
    const clientRunId = params.client_run_id ?? newRunId();
    return this.stream(PATHS.run, { ...compact(params), client_run_id: clientRunId }, clientRunId, options);
  }

  /**
   * Continue a conversation, carrying prior turns and the last synthesis.
   *
   * Streams the same event shape as {@link run}.
   */
  runFollowup(
    params: FollowupParams,
    options: RequestOptions = {},
  ): AsyncGenerator<ReasonerEvent, void> {
    const clientRunId = params.client_run_id ?? newRunId();
    return this.stream(
      PATHS.runFollowup,
      { ...compact(params), client_run_id: clientRunId },
      clientRunId,
      options,
    );
  }

  /**
   * Run a pipeline and return its aggregated outcome.
   *
   * For callers that want the answer rather than the trace. The full event list
   * is retained on {@link RunSummary.events}, so nothing is lost by using this
   * over {@link run}.
   */
  async runToCompletion(params: RunParams, options: RequestOptions = {}): Promise<RunSummary> {
    const clientRunId = params.client_run_id ?? newRunId();
    const events: ReasonerEvent[] = [];

    for await (const event of this.run({ ...params, client_run_id: clientRunId }, options)) {
      events.push(event);
    }

    return summarise(events, clientRunId);
  }

  /**
   * Run a pipeline and let the server collapse the stream to one JSON object.
   *
   * Equivalent to {@link runToCompletion}, minus the client-side event
   * folding — no SSE parser touches this path at all, which is the point for
   * a caller that only wants the answer. The trade-off is
   * {@link RunSummary.events}: there is no stream to keep, so it is always
   * empty here. Use {@link run} or {@link runToCompletion} for per-phase
   * progress or the full trace.
   *
   * @throws {InsufficientCreditsError} when the balance is exhausted (402).
   * @throws {DuplicateRunError} when `client_run_id` is already in flight (409).
   * @throws {RateLimitError} when rate limited past `maxRetries` (429).
   */
  async runSync(params: RunParams, options: RequestOptions = {}): Promise<RunSummary> {
    const clientRunId = params.client_run_id ?? newRunId();
    const wire = await this.http.json<RunResultWire>({
      method: 'POST',
      path: PATHS.runSync,
      body: { ...compact(params), client_run_id: clientRunId },
      clientRunId,
      ...options,
    });
    return fromRunResult(wire, clientRunId);
  }

  /**
   * Ask HyperGate how it would route a problem, without running it.
   *
   * The decision is cached, so a subsequent {@link run} for the same problem
   * does not pay the routing cost twice. Pass the returned `preset` back with
   * `force_pipeline: true` to lock the choice in.
   */
  async gate(
    params: { problem: string; preset?: string },
    options: RequestOptions = {},
  ): Promise<GateResponse> {
    return this.http.json<GateResponse>({
      method: 'POST',
      path: PATHS.gate,
      body: compact(params),
      ...options,
    });
  }

  /** Project tokens, cost, and duration for a run without executing it. */
  async estimate(
    params: { problem: string; preset?: string },
    options: RequestOptions = {},
  ): Promise<EstimateResponse> {
    return this.http.json<EstimateResponse>({
      method: 'POST',
      path: PATHS.estimate,
      body: compact(params),
      ...options,
    });
  }

  /** List every preset with its description and primary model. */
  async presets(options: RequestOptions = {}): Promise<PresetsResponse> {
    return this.http.json<PresetsResponse>({ method: 'GET', path: PATHS.presets, ...options });
  }

  /** List registered model ids, grouped by provider. */
  async models(options: RequestOptions = {}): Promise<ModelsResponse> {
    return this.http.json<ModelsResponse>({ method: 'GET', path: PATHS.models, ...options });
  }

  /** Liveness and dependency status. */
  async health(options: RequestOptions = {}): Promise<Record<string, unknown>> {
    return this.http.json<Record<string, unknown>>({
      method: 'GET',
      path: PATHS.health,
      ...options,
    });
  }

  /** Current credit balance, tier, and monthly allowance. */
  async credits(options: RequestOptions = {}): Promise<CreditsResponse> {
    return this.http.json<CreditsResponse>({ method: 'GET', path: PATHS.credits, ...options });
  }

  /** Credit ledger, newest entries first. */
  async creditLedger(
    params: { limit?: number; offset?: number } = {},
    options: RequestOptions = {},
  ): Promise<LedgerResponse> {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    const qs = query.toString();
    const suffix = qs ? `?${qs}` : '';

    return this.http.json<LedgerResponse>({
      method: 'GET',
      path: `${PATHS.creditsLedger}${suffix}`,
      ...options,
    });
  }

  /** How credits map to money, and the allowance for each tier. */
  async creditPricing(options: RequestOptions = {}): Promise<CreditPricingResponse> {
    return this.http.json<CreditPricingResponse>({
      method: 'GET',
      path: PATHS.creditsPricing,
      ...options,
    });
  }

  /** Shared streaming path for {@link run} and {@link runFollowup}. */
  private async *stream(
    path: string,
    body: Record<string, unknown>,
    clientRunId: string,
    options: RequestOptions,
  ): AsyncGenerator<ReasonerEvent, void> {
    // Abort the transfer when the consumer stops iterating.
    const controller = new AbortController();
    const onCallerAbort = () => controller.abort();
    options.signal?.addEventListener('abort', onCallerAbort, { once: true });

    try {
      const response = await this.http.send({
        method: 'POST',
        path,
        body,
        clientRunId,
        stream: true,
        signal: controller.signal,
        ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
      });

      if (!response.body) {
        throw new ReasonerError('Response carried no body', response.status);
      }

      yield* parseSSE<ReasonerEvent>(response.body, controller.signal);
    } catch (error) {
      if (options.signal?.aborted) throw new AbortError();
      throw error;
    } finally {
      options.signal?.removeEventListener('abort', onCallerAbort);
      controller.abort();
    }
  }
}

/**
 * Map `/api/agent/run/sync`'s wire response onto the same {@link RunSummary}
 * shape {@link summarise} builds from a stream, so callers can switch between
 * {@link ReasonerClient.runSync} and {@link ReasonerClient.runToCompletion}
 * without touching how they read the result.
 *
 * `events` is always empty: the sync endpoint never sent one, so there is
 * nothing to keep. `phaseCosts` is likewise unavailable — that breakdown
 * lives only on the streamed `done` frame, which this path skips entirely.
 */
export function fromRunResult(data: RunResultWire, clientRunId: string): RunSummary {
  return {
    synthesis: data.synthesis,
    criticalInsights: asStringArray(data.critical_insights),
    actionBlueprint: asActionSteps(data.action_blueprint),
    openQuestions: asStringArray(data.open_questions),
    claimLabels: asClaimLabels(data.claim_labels),
    citations: Array.isArray(data.citations) ? data.citations : [],
    costUsd: typeof data.total_cost_usd === 'number' ? data.total_cost_usd : 0,
    phaseCosts: {},
    tokens: data.total_tokens ?? EMPTY_TOKENS,
    durationSeconds: typeof data.duration_seconds === 'number' ? data.duration_seconds : 0,
    modelsUsed: asStringArray(data.models_used),
    errors: [...new Set(asStringArray(data.errors))],
    preset: typeof data.preset === 'string' ? data.preset : undefined,
    method: typeof data.method === 'string' ? data.method : undefined,
    clientRunId,
    events: [],
  };
}

/**
 * Fold a run's events into a {@link RunSummary}.
 *
 * The synthesis is read from the last `phase_complete` carrying a
 * `core_solution`, searching backwards so the final phase wins over any earlier
 * partial. Insights, blueprint, and open questions come from that same payload
 * rather than from the `done` frame, which carries only cost and timing.
 */
export function summarise(events: ReasonerEvent[], clientRunId: string): RunSummary {
  const done = events.find((e): e is DoneEvent => isEvent(e, 'done'));

  let synthesis = '';
  let criticalInsights: string[] = [];
  let actionBlueprint: ActionStep[] = [];
  let openQuestions: string[] = [];
  let claimLabels: ClaimLabels = {};

  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (!event || !isEvent(event, 'phase_complete')) continue;

    const data = event.data;
    if (!data || typeof data !== 'object') continue;

    const core = (data as Record<string, unknown>).core_solution;
    if (typeof core !== 'string' || !core) continue;

    synthesis = core;
    criticalInsights = asStringArray((data as Record<string, unknown>).critical_insights);
    actionBlueprint = asActionSteps((data as Record<string, unknown>).action_blueprint);
    openQuestions = asStringArray((data as Record<string, unknown>).open_questions);
    claimLabels = asClaimLabels((data as Record<string, unknown>).claim_labels);
    break;
  }

  const modelsUsed: string[] = [];
  for (const event of events) {
    if (!isEvent(event, 'phase_complete')) continue;
    const models = event.models ?? (event.data as Record<string, unknown> | undefined)?.models;
    for (const model of asStringArray(models)) {
      if (!modelsUsed.includes(model)) modelsUsed.push(model);
    }
  }

  // Citations ride their own phase — the serializer emits them on a payload
  // carrying no core_solution, so they are not on the synthesis payload the
  // fields above came from. Last non-empty wins, matching the server.
  let citations: Citation[] = [];
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (!event || !isEvent(event, 'phase_complete')) continue;
    const data = event.data as Record<string, unknown> | undefined;
    const found = data?.citations;
    if (Array.isArray(found) && found.length > 0) {
      citations = found.filter((c): c is Citation => typeof c === 'object' && c !== null);
      if (citations.length > 0) break;
    }
  }

  const start = events.find((e) => isEvent(e, 'start'));
  const method = events.find((e) => isEvent(e, 'method_selected'));

  const errors = [
    ...asStringArray(done?.errors),
    ...events
      .filter((e) => isEvent(e, 'error'))
      .map((e) => {
        const err = e as { error?: string | null; message?: string };
        return err.error ?? err.message ?? '';
      })
      .filter(Boolean),
  ];

  return {
    synthesis,
    criticalInsights,
    actionBlueprint,
    openQuestions,
    claimLabels,
    citations,
    costUsd: typeof done?.total_cost_usd === 'number' ? done.total_cost_usd : 0,
    phaseCosts: (done?.phase_costs as Record<string, number> | undefined) ?? {},
    tokens: done?.total_tokens ?? EMPTY_TOKENS,
    durationSeconds: typeof done?.duration === 'number' ? done.duration : 0,
    modelsUsed,
    errors: [...new Set(errors)],
    preset: typeof start?.preset === 'string' ? start.preset : undefined,
    method:
      (typeof method?.method === 'string' ? method.method : undefined) ??
      (typeof start?.auto_selected_method === 'string' ? start.auto_selected_method : undefined) ??
      (typeof start?.method === 'string' ? start.method : undefined),
    clientRunId,
    events,
  };
}
