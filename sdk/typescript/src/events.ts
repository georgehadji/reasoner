/**
 * Event shapes streamed by `POST /api/run` and `POST /api/run-followup`.
 *
 * **The event set is open.** The API adds new `type` values without a version
 * bump, so this union carries an {@link UnknownEvent} arm and every event keeps
 * an index signature. Never `switch` exhaustively on `type` and never treat an
 * unrecognised event as an error — narrow with {@link isEvent} and ignore the
 * rest. An SDK that rejects unknown events would be the thing blocking the API
 * from evolving.
 */

/** Token accounting, reported once on the terminal `done` event. */
export interface TokenCount {
  input: number;
  output: number;
  total: number;
}

/** A reasoning method HyperGate considered but did not select. */
export interface MethodAlternative {
  method: string;
  confidence: number;
  rationale: string;
}

/** Fields shared by every event, including ones this SDK version predates. */
export interface BaseEvent {
  type: string;
  /** Forward compatibility: fields added after this SDK version was published. */
  [key: string]: unknown;
}

/** First event of every run. `auto_selected_method` is set when HyperGate chose. */
export interface StartEvent extends BaseEvent {
  type: 'start';
  preset?: string;
  method?: string;
  auto_selected_method?: string;
}

/** HyperGate's routing decision, emitted once per run. */
export interface MethodSelectedEvent extends BaseEvent {
  type: 'method_selected';
  action?: 'direct' | 'pipeline' | 'web_search';
  method?: string;
  confidence?: number;
  reasoning?: string;
  alternatives?: MethodAlternative[] | null;
}

/** The prompt enhancer rewrote the problem before the pipeline saw it. */
export interface PromptEnhancedEvent extends BaseEvent {
  type: 'prompt_enhanced';
  original?: string;
  enhanced?: string;
}

/** A phase began. `phase` may be fractional (1.5, 2.5, 3.5, 4.25) for sub-phases. */
export interface PhaseStartEvent extends BaseEvent {
  type: 'phase_start';
  phase?: number;
  name?: string;
}

/**
 * A phase finished. `data` holds the phase payload — for the synthesis phase
 * that includes `core_solution`, `critical_insights`, `action_blueprint`,
 * `open_questions`, `claim_labels`, and `evidence`.
 */
export interface PhaseCompleteEvent extends BaseEvent {
  type: 'phase_complete';
  phase?: number;
  name?: string;
  data?: Record<string, unknown>;
  models?: string[];
  cached?: boolean;
}

/** A phase's output was scored by the quality monitor. */
export interface PhaseQualityEvent extends BaseEvent {
  type: 'phase_quality';
  phase?: number;
  score?: number;
  passed?: boolean;
  reason?: string;
}

/** A phase is being retried after failing its quality gate. */
export interface PhaseRetryEvent extends BaseEvent {
  type: 'phase_retry';
  phase?: number;
  attempt?: number;
  max_attempts?: number;
  reason?: string;
}

/**
 * A recoverable error. The stream continues; the run may still reach `done`.
 * Fatal failures also arrive as a `done` event carrying `errors`.
 */
export interface ErrorEvent extends BaseEvent {
  type: 'error';
  error?: string | null;
  message?: string;
  error_type?: string;
  phase?: number;
  retryable?: boolean;
  retry_after?: number;
}

/**
 * Terminal event. Always the last frame of a successful stream.
 *
 * `total_cost_usd` is the authoritative figure charged against credits. On a
 * pipeline crash only `errors` is populated.
 */
export interface DoneEvent extends BaseEvent {
  type: 'done';
  errors?: string[];
  total_tokens?: TokenCount;
  duration?: number;
  total_cost_usd?: number;
  phase_costs?: Record<string, number>;
}

/** The run was cancelled before completing. */
export interface CancelledEvent extends BaseEvent {
  type: 'cancelled';
  message?: string;
}

/** A sub-agent started work within a phase. */
export interface AgentStartEvent extends BaseEvent {
  type: 'agent_start';
  agent?: string;
  role?: string;
  task?: string;
  model?: string;
}

/** A sub-agent finished. */
export interface AgentCompleteEvent extends BaseEvent {
  type: 'agent_complete';
  agent?: string;
  role?: string;
  model?: string;
}

/** Incremental text from a streaming phase. */
export interface TextChunkEvent extends BaseEvent {
  type: 'text_chunk';
  text?: string;
}

/** Long-term memory was recalled and injected into the run. */
export interface RecallUsedEvent extends BaseEvent {
  type: 'recall_used';
  memory_count?: number;
  memory_ids?: string[];
}

/** A step of the Prism research loop (research method only). */
export interface ResearchStepEvent extends BaseEvent {
  type: 'research_step_emitted';
  step_type?: 'searching' | 'reasoning' | 'reading';
  queries?: string[];
  plan?: string;
  urls?: string[];
}

/** Citations gathered by the research loop are ready. */
export interface ResearchCitationsEvent extends BaseEvent {
  type: 'research_citations_ready';
  citation_count?: number;
  source_types?: string[];
}

/** A structured widget result (weather, stocks, calculations). */
export interface WidgetEvent extends BaseEvent {
  type: 'widget';
  name?: string;
  data?: Record<string, unknown>;
}

/**
 * An event type this SDK version does not model.
 *
 * Reaching this arm is expected and benign — the API adds event types without
 * a version bump. Read fields off it defensively or skip it.
 */
export interface UnknownEvent extends BaseEvent {
  type: string;
}

/** Every event this SDK models, plus the open {@link UnknownEvent} arm. */
export type ReasonerEvent =
  | StartEvent
  | MethodSelectedEvent
  | PromptEnhancedEvent
  | PhaseStartEvent
  | PhaseCompleteEvent
  | PhaseQualityEvent
  | PhaseRetryEvent
  | ErrorEvent
  | DoneEvent
  | CancelledEvent
  | AgentStartEvent
  | AgentCompleteEvent
  | TextChunkEvent
  | RecallUsedEvent
  | ResearchStepEvent
  | ResearchCitationsEvent
  | WidgetEvent
  | UnknownEvent;

/** Map from a known `type` string to its event interface. */
export interface EventByType {
  start: StartEvent;
  method_selected: MethodSelectedEvent;
  prompt_enhanced: PromptEnhancedEvent;
  phase_start: PhaseStartEvent;
  phase_complete: PhaseCompleteEvent;
  phase_quality: PhaseQualityEvent;
  phase_retry: PhaseRetryEvent;
  error: ErrorEvent;
  done: DoneEvent;
  cancelled: CancelledEvent;
  agent_start: AgentStartEvent;
  agent_complete: AgentCompleteEvent;
  text_chunk: TextChunkEvent;
  recall_used: RecallUsedEvent;
  research_step_emitted: ResearchStepEvent;
  research_citations_ready: ResearchCitationsEvent;
  widget: WidgetEvent;
}

/** Event type names this SDK version models. */
export type KnownEventType = keyof EventByType;

/**
 * Narrow an event to a known type.
 *
 * Prefer this over `event.type === 'done'`: the union's open arm means a bare
 * equality check does not narrow cleanly, and a type guard keeps unknown events
 * falling through instead of throwing.
 *
 * ```ts
 * for await (const event of client.run({ problem })) {
 *   if (isEvent(event, 'done')) console.log(event.total_cost_usd);
 * }
 * ```
 */
export function isEvent<T extends KnownEventType>(
  event: ReasonerEvent,
  type: T,
): event is EventByType[T] {
  return event.type === type;
}

/** Whether this event terminates the stream. */
export function isTerminal(event: ReasonerEvent): event is DoneEvent | CancelledEvent {
  return event.type === 'done' || event.type === 'cancelled';
}
