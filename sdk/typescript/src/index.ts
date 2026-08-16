/**
 * `@reasoner/sdk` — TypeScript client for the Reasoner API.
 *
 * ```ts
 * import { ReasonerClient, isEvent } from '@reasoner/sdk';
 *
 * const client = new ReasonerClient({ apiKey: process.env.REASONER_API_KEY });
 * const result = await client.runToCompletion({ problem: 'Should we migrate off our monolith?' });
 *
 * console.log(result.synthesis);
 * console.log(`$${result.costUsd.toFixed(4)} across ${result.modelsUsed.length} models`);
 * ```
 */

export { ReasonerClient, fromRunResult, summarise } from './client.js';

export type { ClientOptions, RequestOptions } from './http.js';

export {
  AbortError,
  AuthenticationError,
  BadRequestError,
  ConnectionError,
  DuplicateRunError,
  InsufficientCreditsError,
  PermissionError,
  RateLimitError,
  ReasonerError,
  ServerError,
  formatApiError,
  parseRetryAfter,
} from './errors.js';

export { isEvent, isTerminal } from './events.js';

export type {
  AgentCompleteEvent,
  AgentStartEvent,
  BaseEvent,
  CancelledEvent,
  DoneEvent,
  ErrorEvent,
  EventByType,
  KnownEventType,
  MethodAlternative,
  MethodSelectedEvent,
  PhaseCompleteEvent,
  PhaseQualityEvent,
  PhaseRetryEvent,
  PhaseStartEvent,
  PromptEnhancedEvent,
  ReasonerEvent,
  RecallUsedEvent,
  ResearchCitationsEvent,
  ResearchStepEvent,
  StartEvent,
  TextChunkEvent,
  TokenCount,
  UnknownEvent,
  WidgetEvent,
} from './events.js';

export type {
  ActionStep,
  AttachmentRef,
  ClaimLabels,
  ConversationTurn,
  CreditPricingResponse,
  CreditsResponse,
  EstimateResponse,
  FollowupParams,
  GateResponse,
  LedgerEntry,
  LedgerResponse,
  MethodId,
  ModelsResponse,
  PresetInfo,
  PresetsResponse,
  RunParams,
  RunResultWire,
  RunSummary,
  SourceType,
} from './types.js';

export { frameToData, parseSSE, readFrames } from './sse.js';
